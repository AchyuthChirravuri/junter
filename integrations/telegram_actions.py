"""Telegram role actions through POST /api/action; Python 3.9 stdlib only.

The gateway hook runs before core authorization: it MUST use core authorization
before doing any work. Recognized commands never fall through to an LLM/CSV path.
This module does not import tracker helpers, publish snapshots, or sync CSVs.
"""
import asyncio
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid
from urllib import error, request
from urllib.parse import urlsplit

ALIASES = {
    'int': 'mark_interested', 'pkg': 'mark_packaged', 'sub': 'mark_submitted',
    'blocked': 'mark_blocked', 'block': 'mark_blocked', 'notes': 'edit_notes',
    'gate': 'complete_gate', 'view': 'view',
}
ACTIONS = set(ALIASES.values())
GATES = {'backgrounder_read', 'resume_drafted', 'cover_letter_drafted',
         'references_notified', 'submission_logged'}
LABELS = {
    400: 'validation rejected; no change confirmed',
    401: 'unauthorized; operator configuration required',
    403: 'unauthorized; operator configuration required',
    404: 'role not found in authoritative store',
    409: 'conflict; authoritative state retained, review before a new command',
    429: 'rate limited; wait for cooldown, inspect state, then send a new command',
}


def command_name(text):
    words = text.strip().split(None, 1)
    return words[0].lower() if words else ''


def parse_command(text):
    """Return one operation per role; validate the entire batch before sending."""
    name = command_name(text)
    if name not in ALIASES and name not in ACTIONS:
        return None
    pieces = text.strip().split(None, 1)
    if len(pieces) != 2:
        raise ValueError('command requires role IDs')
    action = ALIASES.get(name, name)
    tail = pieces[1]
    if action in ('edit_notes', 'complete_gate'):
        args = tail.split(None, 1)
        if len(args) != 2:
            raise ValueError('notes/gate requires one ID and a value')
        ids = [args[0]]
        payload = {'notes': args[1]} if action == 'edit_notes' else {'gate': args[1]}
        if action == 'complete_gate' and args[1] not in GATES:
            raise ValueError('unknown gate')
    else:
        ids = tail.replace(',', ' ').replace('<', ' ').replace('>', ' ').split()
        payload = {}
    if not ids or len(ids) > 50:
        raise ValueError('provide 1 to 50 positive integer IDs')
    operations = []
    seen = set()
    for raw in ids:
        if not re.fullmatch(r'[0-9]+', raw) or int(raw) < 1:
            raise ValueError('role IDs must be positive integers')
        rid = int(raw)
        if rid > 9007199254740991:
            raise ValueError('role ID exceeds JSON safe integer range')
        if rid not in seen:
            seen.add(rid)
            operations.append({'action': action, 'role_id': rid, 'payload': payload.copy()})
    return operations


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # never forward a bearer token to another endpoint


class HttpTransport:
    """Credentials/endpoint come from the private gateway process environment."""
    def __init__(self, endpoint, token):
        url = urlsplit(endpoint)
        if (url.scheme != 'https' or not url.netloc or url.path != '/api/action'
                or url.username or url.password or url.query or url.fragment or not token):
            raise ValueError('private HTTPS /api/action endpoint and token required')
        self.endpoint = endpoint
        self.token = token
        self.opener = request.build_opener(NoRedirect())

    def __call__(self, body):
        req = request.Request(self.endpoint, method='POST',
                              data=json.dumps(body).encode('utf-8'),
                              headers={'Content-Type': 'application/json',
                                       'Authorization': 'Bearer ' + self.token})
        try:
            response = self.opener.open(req, timeout=8)
        except error.HTTPError as exc:
            response = exc
        with response:
            status = response.code
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError('oversized response')
            return status, json.loads(raw.decode('utf-8'))

    @classmethod
    def from_environment(cls):
        if os.environ.get('JUNTER_TELEGRAM_ACTIONS_ENABLED') != '1':
            raise ValueError('live action transport disabled')
        return cls(os.environ.get('JUNTER_ACTION_ENDPOINT', ''),
                   os.environ.get('JUNTER_ACTION_TOKEN', ''))


class ActionClient:
    """Private receipt journal: persist UUID BEFORE HTTP; never retry past 55s.

    Locks serialize simultaneous deliveries across threads/processes. Saved
    responses contain only safe feedback/state fields, not raw server errors,
    company data, credentials, or note contents. A message identity must include
    chat + sender + message ID. Editing a message cannot recycle its keys.
    """
    def __init__(self, ledger, transport, clock=time.time, attempts=2):
        self.ledger = Path(ledger)
        self.transport = transport
        self.clock = clock
        self.attempts = attempts

    def _operation(self, identity, fingerprint, index, operation):
        self.ledger.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = str(self.ledger) + '.lock'
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(fd, 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with contextlib.closing(sqlite3.connect(str(self.ledger), timeout=20)) as db:
                os.chmod(self.ledger, 0o600)
                db.execute('CREATE TABLE IF NOT EXISTS receipts '
                           '(identity TEXT, op_index INTEGER, fingerprint TEXT, '
                           'uuid TEXT, first_attempt REAL, result TEXT, '
                           'PRIMARY KEY(identity, op_index))')
                row = db.execute('SELECT fingerprint, uuid, first_attempt, result '
                                 'FROM receipts WHERE identity=? AND op_index=?',
                                 (identity, index)).fetchone()
                if row and row[0] != fingerprint:
                    return {'role_id': operation['role_id'], 'ok': False,
                            'feedback': 'edited replay rejected; send a new message'}
                if row:
                    key, first, saved = row[1:]
                    if saved:
                        result = json.loads(saved)
                        result['message_replay'] = True
                        return result
                    if self.clock() - first >= 55:
                        return {'role_id': operation['role_id'], 'ok': False,
                                'feedback': 'outcome unknown; retry window expired; '
                                            'inspect authoritative state before a new command'}
                else:
                    key, first = str(uuid.uuid4()), self.clock()
                    db.execute('INSERT INTO receipts VALUES (?, ?, ?, ?, ?, NULL)',
                               (identity, index, fingerprint, key, first))
                    db.commit()  # key survives a crash or a lost response
                body = dict(operation, source='telegram', idempotency_key=key)
                result = None
                for attempt in range(self.attempts):
                    if self.clock() - first >= 55:
                        break
                    try:
                        status, response = self.transport(body.copy())
                        result = self._result(operation, status, response)
                    except Exception:
                        # Never echo transport exceptions (may contain credentials/hosts).
                        result = {'role_id': operation['role_id'], 'ok': False,
                                  'retryable': True,
                                  'feedback': 'outcome unknown; network/protocol failure; '
                                              'retry this same message within 55 seconds'}
                    if not result.get('retryable') or result.get('status') == 429:
                        break  # no hot-loop on a server rate limit
                if result is None:
                    result = {'role_id': operation['role_id'], 'ok': False,
                              'retryable': True, 'feedback': 'outcome unknown; retry window expired'}
                if not result.get('retryable'):
                    db.execute('UPDATE receipts SET result=? WHERE identity=? AND op_index=?',
                               (json.dumps(result), identity, index))
                    db.commit()
                return result

    @staticmethod
    def _result(operation, status, response):
        rid = operation['role_id']
        if not isinstance(response, dict) or not isinstance(response.get('ok'), bool):
            raise ValueError('invalid response envelope')
        result = {'role_id': rid, 'status': status, 'ok': False}
        if status == 200 and response['ok'] is True:
            role = response.get('role')
            if (not isinstance(role, dict) or type(role.get('id')) is not int
                    or role['id'] != rid or not response.get('request_id')
                    or not response.get('applied_at')):
                raise ValueError('missing authoritative role or receipt')
            result.update(ok=True,
                          idempotency_replay=response.get('idempotency_replay') is True,
                          feedback='confirmed by shared endpoint',
                          role={k: role[k] for k in ('id', 'status', 'routed', 'gates') if k in role})
            return result
        result['feedback'] = LABELS.get(status, 'server/protocol failure; no change confirmed')
        result['retryable'] = status == 429 or status >= 500
        if status == 409:
            role = response.get('role')
            if isinstance(role, dict) and role.get('id') == rid:
                result['role'] = {k: role[k] for k in ('id', 'status', 'routed') if k in role}
        return result

    def execute(self, text, identity):
        operations = parse_command(text)
        if operations is None:
            raise ValueError('unsupported action command')
        if not identity:
            raise ValueError('stable message identity required')
        fingerprint = hashlib.sha256(json.dumps(operations, sort_keys=True).encode()).hexdigest()
        # Journal only a digest of chat/user/message identity, never raw IDs.
        scope = hashlib.sha256(identity.encode()).hexdigest()
        self.ledger.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(str(self.ledger) + '.lock', os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(fd, 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with contextlib.closing(sqlite3.connect(str(self.ledger), timeout=20)) as db:
                os.chmod(self.ledger, 0o600)
                db.execute('CREATE TABLE IF NOT EXISTS commands (identity TEXT PRIMARY KEY, fingerprint TEXT)')
                row = db.execute('SELECT fingerprint FROM commands WHERE identity=?', (scope,)).fetchone()
                if row and row[0] != fingerprint:
                    return [{'role_id': op['role_id'], 'ok': False,
                             'feedback': 'edited replay rejected; send a new message'} for op in operations]
                db.execute('INSERT OR IGNORE INTO commands VALUES (?, ?)', (scope, fingerprint))
                db.commit()
        return [self._operation(scope, fingerprint, i, op) for i, op in enumerate(operations)]


def feedback(results):
    lines = []
    for result in results:
        line = 'Role %s: %s' % (result['role_id'], result['feedback'])
        if result.get('idempotency_replay') or result.get('message_replay'):
            line += ' (duplicate replay; no new write)'
        role = result.get('role', {})
        state = role.get('routed') or role.get('status')
        if state in ('int', 'pkg', 'sub', 'interested', 'packaged', 'submitted', 'blocked', 'pinged'):
            line += '; state=' + state
        lines.append(line)
    return '\n'.join(lines) + '\nLocal CSV unchanged; CSV-based backgrounder waits for operator sync.'


class GatewayHook:
    def __init__(self, home, client_factory=None):
        self.home = Path(home)
        self.client_factory = client_factory or self._client

    def _client(self):
        return ActionClient(self.home / 'private' / 'junter-action-receipts.sqlite',
                            HttpTransport.from_environment())

    async def __call__(self, event, gateway, **kwargs):
        source = event.source
        platform = getattr(source.platform, 'value', source.platform)
        if (platform != 'telegram' or getattr(event, 'internal', False)
                or command_name(event.text or '') not in set(ALIASES) | ACTIONS):
            return None  # unrelated workflows remain untouched
        # Core hook is PRE-auth: never bypass core allowlist/pairing or bot controls.
        try:
            authorized = gateway._is_user_authorized_for_source(source)
        except Exception:
            return {'action': 'skip', 'reason': 'junter authorization unavailable'}
        if not authorized:
            return None  # let core pairing/decline policy handle unauthorized users
        if getattr(source, 'is_bot', False):
            return {'action': 'skip', 'reason': 'junter bot action denied'}
        if not getattr(event, '_bot_loop_admitted', False):
            try:
                if not gateway._admit_bot_message_for_source(source):
                    return {'action': 'skip', 'reason': 'junter loop admission denied'}
            except Exception:
                return {'action': 'skip', 'reason': 'junter loop admission unavailable'}
        # ALWAYS skip recognized authorized commands, even if parsing/network/send fails.
        reply = 'Shared actions unavailable; no change confirmed. No CSV fallback.'
        try:
            parse_command(event.text)  # before configuration/transport
            mid = getattr(event, 'message_id', None)
            if not mid or not source.chat_id or not source.user_id:
                raise ValueError('stable message identity unavailable')
            identity = json.dumps([str(source.chat_id), str(source.user_id), str(mid)])
            client = self.client_factory()
            results = await asyncio.to_thread(client.execute, event.text, identity)
            reply = feedback(results)
        except ValueError:
            reply = ('Command/configuration rejected; use int/pkg/sub/blocked <positive IDs>, '
                     'notes <ID> <text>, gate <ID> <gate>, or view <IDs>. '
                     'Live transport requires operator configuration. No CSV fallback.')
        except Exception:
            pass
        try:
            adapter = gateway._delivery_adapter_for(source)
            if adapter:
                metadata = {'thread_id': source.thread_id} if getattr(source, 'thread_id', None) else None
                await adapter.send(source.chat_id, reply, reply_to=event.message_id, metadata=metadata)
        except Exception:
            # Persisted receipts make redelivery safe; never hand the action to the LLM.
            pass
        return {'action': 'skip', 'reason': 'junter shared action handled'}

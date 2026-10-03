"""Mock-only Telegram integration tests. No live transport or tracker helpers."""
import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from integrations.telegram_actions import (
    ActionClient, GatewayHook, HttpTransport, feedback, parse_command,
)


class MockTransport:
    def __init__(self, sequence=None):
        self.calls = []
        self.sequence = list(sequence or [])

    def __call__(self, body):
        self.calls.append(json.loads(json.dumps(body)))
        if self.sequence:
            item = self.sequence.pop(0)
            if isinstance(item, Exception):
                raise item
            if item is not None:
                return item
        return 200, {'ok': True, 'request_id': 'receipt',
                     'applied_at': '2026-10-02T20:00:00Z',
                     'role': {'id': body['role_id'], 'routed': 'int',
                              'status': 'interested'}, 'idempotency_replay': False}


class TelegramActionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Path(self.tmp.name) / 'private' / 'receipts.sqlite'

    def client(self, transport=None, **kwargs):
        return ActionClient(self.ledger, transport or MockTransport(), **kwargs)

    def test_int_batch_contract_unique_uuids(self):
        transport = MockTransport()
        result = self.client(transport).execute('int 3 5 7', 'chat-user-msg')
        self.assertEqual([c['role_id'] for c in transport.calls], [3, 5, 7])
        self.assertTrue(all(r['ok'] for r in result))
        for body in transport.calls:
            self.assertEqual(set(body), {'action', 'role_id', 'payload', 'source', 'idempotency_key'})
            self.assertEqual(body['source'], 'telegram')
            self.assertEqual(body['action'], 'mark_interested')
            self.assertEqual(body['payload'], {})
            self.assertEqual(str(uuid.UUID(body['idempotency_key'])), body['idempotency_key'])
        self.assertEqual(len({c['idempotency_key'] for c in transport.calls}), 3)

    def test_retry_same_payload_and_uuid(self):
        transport = MockTransport([TimeoutError('secret host'), None])
        self.assertTrue(self.client(transport).execute('int 3', 'msg')[0]['ok'])
        self.assertEqual(transport.calls[0], transport.calls[1])

    def test_restart_retry_retains_uuid(self):
        transport = MockTransport([TimeoutError(), TimeoutError(), None])
        result = self.client(transport).execute('int 3', 'msg')
        self.assertFalse(result[0]['ok'])
        self.assertTrue(self.client(transport).execute('int 3', 'msg')[0]['ok'])
        self.assertEqual(len({c['idempotency_key'] for c in transport.calls}), 1)

    def test_duplicate_message_does_not_send_again_even_after_window(self):
        transport = MockTransport()
        self.client(transport).execute('int 3', 'msg')
        result = self.client(transport, clock=lambda: 99999999999).execute('int 3', 'msg')
        self.assertEqual(len(transport.calls), 1)
        self.assertTrue(result[0]['message_replay'])
        self.assertIn('no new write', feedback(result))

    def test_uncertain_old_attempt_never_mints_fresh_key(self):
        transport = MockTransport([TimeoutError(), TimeoutError()])
        self.client(transport, clock=lambda: 100).execute('int 3', 'msg')
        result = self.client(transport, clock=lambda: 155).execute('int 3', 'msg')
        self.assertEqual(len(transport.calls), 2)
        self.assertIn('expired', result[0]['feedback'])

    def test_server_idempotency_replay_feedback(self):
        transport = MockTransport([(200, {'ok': True, 'role': {'id': 3},
                                         'request_id': 'original',
                                         'applied_at': '2026-10-02T20:00:00Z',
                                         'idempotency_replay': True})])
        result = self.client(transport).execute('pkg 3', 'msg')
        self.assertIn('duplicate replay', feedback(result))
        self.assertTrue(result[0]['ok'])

    def test_all_supported_actions_payloads(self):
        cases = {'pkg 3': ('mark_packaged', {}), 'sub 3': ('mark_submitted', {}),
                 'blocked 3': ('mark_blocked', {}),
                 'notes 3 A careful note': ('edit_notes', {'notes': 'A careful note'}),
                 'gate 3 backgrounder_read': ('complete_gate', {'gate': 'backgrounder_read'}),
                 'view 3': ('view', {})}
        for command, (action, payload) in cases.items():
            with self.subTest(command=command):
                operation = parse_command(command)[0]
                self.assertEqual(operation, {'action': action, 'role_id': 3, 'payload': payload})

    def test_strict_parse_whole_batch_before_transport(self):
        transport = MockTransport()
        for text in ('int', 'int 3 abc', 'int 3 12.5', 'int 0', 'int -3',
                     'gate 3 fake', 'notes 3', 'int 9007199254740992'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.client(transport).execute(text, text)
        self.assertEqual(transport.calls, [])
        self.assertEqual([o['role_id'] for o in parse_command('int <3>, 5 3')], [3, 5])
        self.assertIsNone(parse_command('research this company'))

    def test_failures_sanitized_with_partial_batch(self):
        for status in (400, 401, 403, 404, 409, 429, 500):
            with self.subTest(status=status):
                transport = MockTransport([(status, {'ok': False, 'error': {
                    'code': 'anything', 'message': 'token=secret https://internal.invalid'},
                    'role': {'id': 3, 'status': 'submitted', 'routed': 'sub'}})] * 2)
                result = self.client(transport).execute('int 3 5', 'status-%s' % status)
                text = feedback(result)
                self.assertNotIn('secret', text)
                self.assertNotIn('internal.invalid', text)
                self.assertFalse(result[0]['ok'])
                if status == 409:
                    self.assertIn('state=sub', text)
                    self.assertEqual(len(transport.calls), 2)
                if status == 404:
                    self.assertIn('not found', text)
                if status == 400:
                    self.assertIn('validation', text)
                if status == 429:
                    self.assertEqual(len(transport.calls), 2)

    def test_malformed_success_and_mismatched_role_not_acknowledged(self):
        for response in ({'ok': True}, {'ok': True, 'role': {'id': 9}},
                         {'ok': 'yes'}, {'ok': True, 'role': {'id': 3}}):
            transport = MockTransport([(200, response)] * 2)
            result = self.client(transport).execute('int 3', json.dumps(response))
            self.assertFalse(result[0]['ok'])
            self.assertIn('outcome unknown', result[0]['feedback'])

    def test_edited_message_does_not_reuse_receipt(self):
        transport = MockTransport()
        self.client(transport).execute('int 3', 'msg')
        result = self.client(transport).execute('sub 3', 'msg')
        self.assertEqual(len(transport.calls), 1)
        self.assertIn('edited replay rejected', result[0]['feedback'])
        expanded = self.client(transport).execute('int 3 5', 'msg')
        self.assertEqual(len(transport.calls), 1)
        self.assertTrue(all('edited replay rejected' in item['feedback'] for item in expanded))

    def test_concurrent_delivery_sends_once(self):
        transport = MockTransport()
        barrier = threading.Barrier(2)
        results = []
        errors = []
        def run():
            try:
                barrier.wait()
                results.append(self.client(transport).execute('int 3', 'same-msg'))
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(errors, [])
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(len(results), 2)

    def test_private_journal_no_notes_or_raw_identity(self):
        self.client().execute('notes 3 private note text', 'private-chat-identity')
        with sqlite3.connect(str(self.ledger)) as db:
            row = db.execute('SELECT * FROM receipts').fetchone()
        self.assertNotIn('private note text', str(row))
        self.assertNotIn('private-chat-identity', str(row))
        self.assertEqual(self.ledger.stat().st_mode & 0o777, 0o600)

    def test_http_post_target_headers_no_redirect(self):
        transport = HttpTransport('https://example.invalid/api/action', 'mock-only-token')
        class Response:
            code = 404
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return b'{"ok": false}'
        with patch.object(transport.opener, 'open', return_value=Response()) as opened:
            status, response = transport({'source': 'telegram'})
        req = opened.call_args[0][0]
        self.assertEqual(req.get_method(), 'POST')
        self.assertEqual(req.full_url, 'https://example.invalid/api/action')
        self.assertEqual(req.get_header('Authorization'), 'Bearer mock-only-token')
        self.assertEqual(json.loads(req.data), {'source': 'telegram'})
        self.assertEqual(status, 404)
        for endpoint in ('http://example.invalid/api/action', 'https://example.invalid/api/other',
                         'https://user:pw@example.invalid/api/action',
                         'https://example.invalid/api/action?token=x'):
            with self.assertRaises(ValueError):
                HttpTransport(endpoint, 'mock')
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(ValueError):
            HttpTransport.from_environment()

    def test_tracker_unchanged(self):
        # Read only a digest, never parse or copy operator PII.
        tracker = Path.home() / 'Hermes-workspace/projects/job-applications/tracker.csv'
        before = hashlib.sha256(tracker.read_bytes()).digest() if tracker.exists() else None
        self.client().execute('int 3 5 7', 'fixture-message')
        after = hashlib.sha256(tracker.read_bytes()).digest() if tracker.exists() else None
        self.assertEqual(before, after)


class GatewayHookTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.transport = MockTransport()
        self.client = ActionClient(Path(self.tmp.name) / 'receipt.sqlite', self.transport)
        self.hook = GatewayHook(self.tmp.name, client_factory=lambda: self.client)
        self.sent = []
        async def send(chat, reply, **kwargs):
            self.sent.append((chat, reply, kwargs))
        self.gateway = SimpleNamespace(
            _is_user_authorized_for_source=lambda source: True,
            _admit_bot_message_for_source=lambda source: True,
            _delivery_adapter_for=lambda source: SimpleNamespace(send=send))
        self.event = SimpleNamespace(text='int 3 5 7', internal=False, message_id='message',
                                     source=SimpleNamespace(platform=SimpleNamespace(value='telegram'),
                                                            chat_id='mock-chat', user_id='mock-user',
                                                            thread_id='topic', is_bot=False))

    async def test_gateway_consumes_command_and_duplicate(self):
        result = await self.hook(self.event, self.gateway)
        self.assertEqual(result['action'], 'skip')
        await self.hook(self.event, self.gateway)
        self.assertEqual(len(self.transport.calls), 3)
        self.assertEqual(len(self.sent), 2)
        self.assertIn('duplicate replay', self.sent[1][1])
        self.assertEqual(self.sent[0][2]['metadata'], {'thread_id': 'topic'})

    async def test_unauthorized_is_left_to_core_without_transport(self):
        self.gateway._is_user_authorized_for_source = lambda source: False
        self.assertIsNone(await self.hook(self.event, self.gateway))
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.sent, [])

    async def test_other_platforms_unrelated_and_internal_untouched(self):
        for text, platform, internal in [('research 3', 'telegram', False),
                                         ('int 3', 'discord', False), ('int 3', 'telegram', True)]:
            self.event.text, self.event.source.platform.value, self.event.internal = text, platform, internal
            self.assertIsNone(await self.hook(self.event, self.gateway))
        self.assertEqual(self.transport.calls, [])

    async def test_rejection_never_falls_back_to_llm_csv(self):
        self.event.text = 'int 3 abc'
        self.assertEqual((await self.hook(self.event, self.gateway))['action'], 'skip')
        self.assertEqual(self.transport.calls, [])
        self.assertIn('No CSV fallback', self.sent[0][1])
        self.hook.client_factory = lambda: (_ for _ in ()).throw(ValueError('private endpoint secret'))
        self.event.text = 'int 3'
        self.assertEqual((await self.hook(self.event, self.gateway))['action'], 'skip')
        self.assertNotIn('secret', self.sent[-1][1])

    async def test_bots_and_missing_authorization_fail_closed(self):
        self.event.source.is_bot = True
        self.assertEqual((await self.hook(self.event, self.gateway))['action'], 'skip')
        self.event.source.is_bot = False
        del self.gateway._is_user_authorized_for_source
        self.assertEqual((await self.hook(self.event, self.gateway))['action'], 'skip')
        self.assertEqual(self.transport.calls, [])

    async def test_failed_reply_delivery_never_falls_through(self):
        async def fail(*args, **kwargs): raise OSError('mock failure')
        self.gateway._delivery_adapter_for = lambda source: SimpleNamespace(send=fail)
        self.assertEqual((await self.hook(self.event, self.gateway))['action'], 'skip')
        self.assertEqual(len(self.transport.calls), 3)
        await self.hook(self.event, self.gateway)
        self.assertEqual(len(self.transport.calls), 3)


if __name__ == '__main__':
    unittest.main()

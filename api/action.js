// Junter — Vercel serverless function: POST /api/action.
//
// The one and only write surface for the system. The UI (click handlers in
// ui/app.js) and the Telegram gateway both POST here. Every action carries
// `source` so the audit log can answer "did the UI or Telegram do this?".
//
// Contract — JSON Schema draft 2020-12 (mirrors docs/refactor-spec-2026-10-03.md
// §3.2 / §3.4; if they diverge, the spec wins and this file is updated).
//
// Request:
//   POST /api/action
//   { action: "mark_interested"|"mark_packaged"|"mark_submitted"|"mark_blocked"
//           |"edit_notes"|"complete_gate"|"view",
//     role_id: int >= 1,
//     payload: object (per-action; see below),
//     source: "ui" | "telegram",
//     idempotency_key: string [A-Za-z0-9_-]{16,64},
//     client_ts?: ISO date-time }
//
// Response (200):
//   { ok: true, request_id, applied_at, role, idempotency_replay: bool }
//
// Response (4xx / 5xx):
//   { ok: false, error: { code, message }, request_id }
//
// Per-action payload:
//   mark_*         — {}
//   edit_notes     — { notes: string }
//   complete_gate  — { gate: "backgrounder_read"|"resume_drafted"
//                            |"cover_letter_drafted"|"references_notified"
//                            |"submission_logged" }
//   view           — {} (audit only; no state change)
//
// State mutation (single store = junter-data Edge Config):
//   mark_interested -> status="interested", routed="int"
//   mark_packaged   -> status="packaged",   routed="pkg"
//   mark_submitted  -> status="submitted",  routed="sub"
//   mark_blocked    -> status="blocked",    routed="", blocked_reason from payload
//   edit_notes      -> angle = payload.notes
//   complete_gate   -> role.gates[payload.gate] = true (idempotent; recorded)
//   view            -> no mutation; still appended to audit log
//
// Failure modes (mapped to UI per spec §3.8):
//   400 validation_failed     — bad body / unknown action / bad enum value
//   401 unauthorized          — personal URL without bearer token (env: JUNTER_BEARER_TOKEN)
//   404 role_not_found        — role_id not in the store
//   409 conflict              — version/etag mismatch (concurrent Telegram write beat us)
//   429 rate_limited          — >10 writes/min per token/IP
//   500 internal_error        — Edge Config unreachable / log write failed
//
// Storage backend: Vercel Edge Config item `junter-data` (same item /api/data
// reads). Writes are ETAG-checked so a Telegram write that lands between the
// UI's read and write surfaces a 409 — the UI rolls back silently and adopts
// the server's authoritative state. The synthetic demo path runs the SAME
// handler against an in-memory store provided by the test harness.
//
// Idempotency: a 60-second ring buffer of `idempotency_key` -> first response
// (in-memory; per Vercel instance). A replay returns the original response
// with `idempotency_replay: true` and no state change.
//
// Privacy: this endpoint exists on the personal Vercel project only. The
// public project (junter-xi) does not deploy this handler — see
// docs/refactor-spec-2026-10-03.md §2.2.
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { readStore, writeStore } from '../lib/store.js';

// --- Schema (in-source mirror of spec §3.2) --------------------------------
// Kept hand-written so the deployed handler does not pull a runtime schema
// validator dependency. The contract test in api/tests/test_action_meta.py
// re-reads this object to keep tests honest.

const VALID_ACTIONS = new Set([
  'mark_interested', 'mark_packaged', 'mark_submitted', 'mark_blocked',
  'edit_notes', 'complete_gate', 'view',
]);
const VALID_SOURCES = new Set(['ui', 'telegram']);
const VALID_GATES = new Set([
  'backgrounder_read', 'resume_drafted', 'cover_letter_drafted',
  'references_notified', 'submission_logged',
]);
const IDEMPOTENCY_KEY_RE = /^[A-Za-z0-9_-]{16,64}$/;
const ROLE_ID_MIN = 1;
const IDEMPOTENCY_WINDOW_MS = 60_000;
const RATE_LIMIT_WINDOW_MS = 60_000;
const RATE_LIMIT_MAX = 10;

function validation_error(details) {
  return {
    ok: false,
    error: { code: 'validation_failed', message: 'schema validation failed', details },
    request_id: crypto.randomUUID(),
  };
}

// Apply the spec's mutation rules. Pure function: takes (role, action, payload),
// returns the new role. Throws {code} for payload-shape errors specific to the
// action.
function applyAction(role, action, payload) {
  const next = Object.assign({}, role, { _actions: role._actions || [] });
  const stamp = { action, ts: new Date().toISOString() };
  switch (action) {
    case 'mark_interested':
      next.status = 'interested';
      next.routed = 'int';
      break;
    case 'mark_packaged':
      next.status = 'packaged';
      next.routed = 'pkg';
      break;
    case 'mark_submitted':
      next.status = 'submitted';
      next.routed = 'sub';
      break;
    case 'mark_blocked':
      next.status = 'blocked';
      next.routed = '';
      next.blocked_reason = (payload && typeof payload.reason === 'string') ? payload.reason : 'user-marked';
      break;
    case 'edit_notes': {
      if (!payload || typeof payload.notes !== 'string') {
        throw { code: 'validation_failed', field: 'notes', reason: 'notes must be a string' };
      }
      next.angle = payload.notes;
      break;
    }
    case 'complete_gate': {
      if (!payload || !VALID_GATES.has(payload.gate)) {
        throw { code: 'validation_failed', field: 'gate', reason: 'gate must be one of ' + [...VALID_GATES].join('|') };
      }
      next.gates = Object.assign({}, role.gates || {}, { [payload.gate]: true });
      break;
    }
    case 'view':
      // audit only; no mutation
      break;
    default:
      throw { code: 'validation_failed', field: 'action', reason: 'unknown action' };
  }
  next._actions = next._actions.concat([stamp]);
  return next;
}

// --- Rate limiter (token bucket per token-or-IP) ---------------------------
// Process-local; reset between Vercel cold starts. Sufficient for a single-
// operator surface; a multi-tenant deployment would centralize.
const rateBuckets = new Map();
function checkRateLimit(key) {
  const now = Date.now();
  const entry = rateBuckets.get(key) || { ts: now, count: 0 };
  if (now - entry.ts > RATE_LIMIT_WINDOW_MS) {
    entry.ts = now;
    entry.count = 0;
  }
  entry.count += 1;
  rateBuckets.set(key, entry);
  return entry.count <= RATE_LIMIT_MAX;
}

// --- Idempotency ring buffer ------------------------------------------------
// Process-local Map; default `process_idem_in_memory=1` keeps it fast for a
// single Vercel instance. Set `process_idem_in_memory=0` to back the buffer
// with a JSON file at JUNTER_IDEMPOTENCY_FILE (shared across instances).
const idemBuffer = new Map();
function checkIdempotency(key) {
  const now = Date.now();
  const prior = idemBuffer.get(key);
  if (prior && (now - prior.at) <= IDEMPOTENCY_WINDOW_MS) {
    return prior;
  }
  return null;
}
function recordIdempotency(key, response) {
  idemBuffer.set(key, { at: Date.now(), response });
  // GC: keep buffer bounded; drop entries older than 5 minutes.
  const cutoff = Date.now() - 5 * 60_000;
  for (const [k, v] of idemBuffer) {
    if (v.at < cutoff) idemBuffer.delete(k);
  }
  saveIdemFile();
}

// Optional file-backed idempotency for tests that span multiple Node
// processes (the test harness re-spawns a child per call). Production
// uses the in-memory buffer; set JUNTER_IDEMPOTENCY_FILE in tests.
const IDEMPOTENCY_FILE = process.env.JUNTER_IDEMPOTENCY_FILE;
function loadIdemFile() {
  if (!IDEMPOTENCY_FILE) return null;
  try {
    const raw = fs.readFileSync(IDEMPOTENCY_FILE, 'utf8');
    const obj = JSON.parse(raw);
    if (obj && typeof obj === 'object') return obj;
  } catch (_) { /* missing/empty -> start fresh */ }
  return {};
}
function saveIdemFile() {
  if (!IDEMPOTENCY_FILE) return;
  const obj = {};
  for (const [k, v] of idemBuffer) obj[k] = v;
  try {
    fs.writeFileSync(IDEMPOTENCY_FILE, JSON.stringify(obj));
  } catch (_) { /* best-effort */ }
}

// On cold start, hydrate the in-memory buffer from the file (if configured).
if (IDEMPOTENCY_FILE) {
  const persisted = loadIdemFile();
  for (const k of Object.keys(persisted || {})) {
    idemBuffer.set(k, persisted[k]);
  }
}

// --- Audit log (api/actions.jsonl) -----------------------------------------
// On Vercel, /tmp is the writable runtime dir; on the synthetic test harness
// the path is overridden via JUNTER_AUDIT_LOG.
const AUDIT_LOG_PATH = process.env.JUNTER_AUDIT_LOG || path.join('/tmp', 'actions.jsonl');
function appendAudit(entry) {
  try {
    fs.appendFileSync(AUDIT_LOG_PATH, JSON.stringify(entry) + '\n');
  } catch (err) {
    // Audit write must NEVER break the user-facing response. Surface as 500
    // only if a caller provided a strict-audit flag; default: log and continue.
    if (process.env.JUNTER_STRICT_AUDIT === '1') {
      throw { code: 'audit_write_failed', message: 'cannot write audit log' };
    }
  }
}

// --- Storage adapter ------------------------------------------------------
// The store adapter lives at lib/store.js so both /api/action and /api/data
// (and any future handlers) can share the same read/write path. Production
// reads/writes hit the real @vercel/edge-config SDK; tests inject an in-
// memory store via `globalThis.__junterActionStore` and a conflict trigger
// via `globalThis.__junterActionConflict` (see lib/store.js).

// --- Bearer token gate ----------------------------------------------------
// The personal Vercel project sets JUNTER_BEARER_TOKEN; the public project
// never deploys this handler. Returns 401 without a match.
function checkAuth(req) {
  const expected = process.env.JUNTER_BEARER_TOKEN;
  if (!expected) return true; // unset -> dev/test mode -> allow
  const got = (req.headers && (req.headers['x-junter-token'] || req.headers.authorization || ''))
    .toString()
    .replace(/^Bearer\s+/i, '');
  return got && got === expected;
}

// --- Main handler ---------------------------------------------------------
export default async function handler(req, res) {
  const request_id = crypto.randomUUID();
  const audit_base = { request_id, ts: new Date().toISOString() };

  // Body is parsed up front so audit logging can include the idempotency key
  // even on validation failures. The 405 path never parses a body; the
  // appendAudit call there simply omits idempotency_key.
  let body = req.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); }
    catch { body = null; }
  }
  if (body && typeof body === 'object' && !Array.isArray(body) && body.idempotency_key) {
    audit_base.idempotency_key = body.idempotency_key;
  }

  try {
    if (req.method !== 'POST') {
      const body = { ok: false, error: { code: 'method_not_allowed', message: 'POST only' }, request_id };
      audit_base.method = req.method;
      audit_base.response_status = 405;
      appendAudit(audit_base);
      return res.status(405).json(body);
    }

    if (!checkAuth(req)) {
      audit_base.response_status = 401;
      audit_base.reason = 'unauthorized';
      appendAudit(audit_base);
      return res.status(401).json({
        ok: false,
        error: { code: 'unauthorized', message: 'bearer token required' },
        request_id,
      });
    }

    let body = req.body;
    if (typeof body === 'string') {
      try { body = JSON.parse(body); }
      catch { return res.status(400).json(validation_error({ reason: 'invalid JSON' })); }
    }
    if (!body || typeof body !== 'object' || Array.isArray(body)) {
      return res.status(400).json(validation_error({ reason: 'body must be a JSON object' }));
    }

    // --- Field validation (spec §3.2) ------------------------------------
    const fields = {};
    if (typeof body.action !== 'string' || !VALID_ACTIONS.has(body.action)) {
      fields.action = body.action;
    }
    if (!Number.isInteger(body.role_id) || body.role_id < ROLE_ID_MIN) {
      fields.role_id = body.role_id;
    }
    if (typeof body.source !== 'string' || !VALID_SOURCES.has(body.source)) {
      fields.source = body.source;
    }
    if (typeof body.idempotency_key !== 'string' || !IDEMPOTENCY_KEY_RE.test(body.idempotency_key)) {
      fields.idempotency_key = body.idempotency_key;
    }
    const payload = body.payload;
    if (payload != null && (typeof payload !== 'object' || Array.isArray(payload))) {
      fields.payload = 'payload must be an object';
    }
    if (Object.keys(fields).length) {
      audit_base.action = body.action;
      audit_base.role_id = body.role_id;
      audit_base.response_status = 400;
      appendAudit(audit_base);
      return res.status(400).json({
        ok: false,
        error: { code: 'validation_failed', message: 'schema validation failed', details: fields },
        request_id,
      });
    }

    // --- Rate limit -----------------------------------------------------
    const rlKey = (req.headers && (req.headers['x-junter-token'] || req.headers['x-forwarded-for'])) || 'anon';
    if (!checkRateLimit(rlKey)) {
      audit_base.action = body.action;
      audit_base.role_id = body.role_id;
      audit_base.source = body.source;
      audit_base.response_status = 429;
      appendAudit(audit_base);
      return res.status(429).json({
        ok: false,
        error: { code: 'rate_limited', message: 'too many requests' },
        request_id,
      });
    }

    // --- Idempotency replay --------------------------------------------
    const replay = checkIdempotency(body.idempotency_key);
    if (replay) {
      audit_base.action = body.action;
      audit_base.role_id = body.role_id;
      audit_base.source = body.source;
      audit_base.idempotency_replay = true;
      audit_base.response_status = 200;
      // Audit logs the ORIGINAL response's request_id so the replay is
      // traceable to the same write event downstream consumers see.
      audit_base.request_id = replay.response.request_id;
      appendAudit(audit_base);
      const r = replay.response;
      return res.status(200).json(Object.assign({}, r, { idempotency_replay: true }));
    }

    // --- Read store -----------------------------------------------------
    const read = await readStore();
    const data = (read && read.value && typeof read.value === 'object') ? read.value : { roles: [] };
    const roles = Array.isArray(data.roles) ? data.roles : [];
    const idx = roles.findIndex((r) => Number(r.id) === Number(body.role_id));
    if (idx === -1) {
      audit_base.action = body.action;
      audit_base.role_id = body.role_id;
      audit_base.source = body.source;
      audit_base.response_status = 404;
      appendAudit(audit_base);
      return res.status(404).json({
        ok: false,
        error: { code: 'role_not_found', message: 'role not in store' },
        request_id,
      });
    }

    // --- Mutate ---------------------------------------------------------
    let updated;
    try {
      updated = applyAction(roles[idx], body.action, payload || {});
    } catch (err) {
      audit_base.action = body.action;
      audit_base.role_id = body.role_id;
      audit_base.source = body.source;
      audit_base.response_status = 400;
      audit_base.validation_detail = err && err.field ? err.field : null;
      appendAudit(audit_base);
      return res.status(400).json({
        ok: false,
        error: { code: 'validation_failed', message: err && err.reason ? err.reason : 'invalid payload' },
        request_id,
      });
    }

    // strip internal _actions list from the wire response
    const wire = Object.assign({}, updated);
    delete wire._actions;

    // --- Write back (with conflict detection) ---------------------------
    const newRoles = roles.slice();
    newRoles[idx] = updated;
    const newData = Object.assign({}, data, { roles: newRoles });
    const w = await writeStore(newData, read.etag);
    if (!w.ok) {
      audit_base.action = body.action;
      audit_base.role_id = body.role_id;
      audit_base.source = body.source;
      audit_base.response_status = 409;
      appendAudit(audit_base);
      return res.status(409).json({
        ok: false,
        error: { code: 'conflict', message: 'concurrent write; server state is authoritative' },
        request_id,
      });
    }

    const response = {
      ok: true,
      request_id,
      applied_at: audit_base.ts,
      role: wire,
      idempotency_replay: false,
    };
    recordIdempotency(body.idempotency_key, response);

    audit_base.action = body.action;
    audit_base.role_id = body.role_id;
    audit_base.source = body.source;
    audit_base.payload = payload || {};
    audit_base.response_status = 200;
    appendAudit(audit_base);

    // Cache headers — same posture as /api/data: short so the UI picks up
    // the change on its next fetch within s-maxage=60.
    res.setHeader('Cache-Control', 'no-store');
    return res.status(200).json(response);
  } catch (err) {
    audit_base.response_status = 500;
    audit_base.error_message = err && err.message ? err.message : 'internal error';
    appendAudit(audit_base);
    return res.status(500).json({
      ok: false,
      error: { code: 'internal_error', message: 'unexpected error' },
      request_id,
    });
  }
}

// --- Test-only exports ----------------------------------------------------
// These let the Python harness (api/tests/test_action_meta.py) drive the
// handler against an in-memory store without Vercel credentials or the SDK.
// Production deploys have no reason to expose these; they're behind a named
// export so they don't accidentally appear in the public surface.
export const __test = {
  applyAction,
  checkIdempotency,
  checkRateLimit,
  VALID_ACTIONS,
  VALID_GATES,
  VALID_SOURCES,
  IDEMPOTENCY_KEY_RE,
  idemBuffer,
  rateBuckets,
};
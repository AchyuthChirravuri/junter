// POST /api/action. Local contract implementation; production writes fail
// closed until durable audit and distributed CAS are supplied. See docs.
import crypto from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { readStore, writeStore, storeContext } from '../lib/store.js';
import { getSyntheticStore } from '../lib/transactional-store.js';

const VALID_ACTIONS = new Set(['mark_interested', 'mark_packaged', 'mark_submitted', 'mark_blocked', 'edit_notes', 'complete_gate', 'view']);
const VALID_GATES = new Set(['backgrounder_read', 'resume_drafted', 'cover_letter_drafted', 'references_notified', 'submission_logged']);
const VALID_SOURCES = new Set(['ui', 'telegram']);
const IDEMPOTENCY_KEY_RE = /^[A-Za-z0-9_-]{16,64}$/;
const directory = path.dirname(fileURLToPath(import.meta.url));
const idemBuffer = new Map();
const rateBuckets = new Map();
let queue = Promise.resolve();

function validate(body) {
  const details = {};
  if (!body || typeof body !== 'object' || Array.isArray(body)) return { body: 'JSON object required' };
  for (const key of Object.keys(body)) {
    if (!['action', 'role_id', 'payload', 'source', 'idempotency_key', 'client_ts'].includes(key)) details[key] = 'unknown field';
  }
  if (!VALID_ACTIONS.has(body.action)) details.action = 'unsupported action';
  if (!Number.isSafeInteger(body.role_id) || body.role_id < 1) details.role_id = 'positive integer required';
  if (!VALID_SOURCES.has(body.source)) details.source = 'ui or telegram required';
  if (typeof body.idempotency_key !== 'string' || !IDEMPOTENCY_KEY_RE.test(body.idempotency_key)) details.idempotency_key = '16-64 alphanumeric, underscore or hyphen characters required';
  if (body.client_ts !== undefined && (typeof body.client_ts !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(body.client_ts) || !Number.isFinite(Date.parse(body.client_ts)))) details.client_ts = 'RFC3339 timestamp required';
  const payload = body.payload === undefined ? {} : body.payload;
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    details.payload = 'object required';
  } else {
    const allowed = body.action === 'edit_notes' ? ['notes'] : body.action === 'complete_gate' ? ['gate'] : body.action === 'mark_blocked' ? ['reason'] : [];
    for (const key of Object.keys(payload)) if (!allowed.includes(key)) details[`payload.${key}`] = 'unknown payload field';
    if (body.action === 'edit_notes' && typeof payload.notes !== 'string') details['payload.notes'] = 'string required';
    if (body.action === 'complete_gate' && !VALID_GATES.has(payload.gate)) details['payload.gate'] = 'supported gate required';
    if (payload.reason !== undefined && (typeof payload.reason !== 'string' || !payload.reason.trim())) details['payload.reason'] = 'nonempty string required';
  }
  return details;
}

function applyAction(role, action, payload = {}) {
  const next = structuredClone(role);
  if (action === 'view') return next;
  const statuses = { mark_interested: ['interested', 'int'], mark_packaged: ['packaged', 'pkg'], mark_submitted: ['submitted', 'sub'], mark_blocked: ['blocked', ''] };
  if (statuses[action]) {
    [next.status, next.routed] = statuses[action];
    next.status_date = new Date().toISOString().slice(0, 10);
    next.blocked_reason = action === 'mark_blocked' ? (payload.reason || 'user-marked') : '';
  }
  if (action === 'edit_notes') {
    next.angle = payload.notes;
    if (next.company_research?.application_strategy) next.company_research.application_strategy.angle = payload.notes;
  }
  if (action === 'complete_gate') next.gates = { ...(role.gates || {}), [payload.gate]: true };
  next._actions = [...(role._actions || []), { action, ts: new Date().toISOString() }];
  return next;
}

function wire(role) {
  if (!role) return null;
  const copy = structuredClone(role);
  delete copy._actions;
  return copy;
}

function appendAudit(entry) {
  // Vercel's deployment filesystem is read-only; /tmp is ephemeral. No
  // Python/flock portability or durable repository path is guaranteed there.
  if (process.env.VERCEL) throw new Error('durable flocked audit unavailable on Vercel');
  const helper = path.join(directory, '../lib/audit-append.py');
  const target = process.env.JUNTER_AUDIT_LOG || path.join(directory, 'actions.jsonl');
  const result = spawnSync('python3', [helper, target], { input: JSON.stringify(entry), encoding: 'utf8', timeout: 10000 });
  if (result.error || result.status !== 0) throw new Error('audit append unavailable');
}

function checkRateLimit(key) {
  const now = Date.now();
  for (const [k, v] of rateBuckets) if (now - v.ts >= 60000) rateBuckets.delete(k);
  const entry = rateBuckets.get(key) || { ts: now, count: 0 };
  entry.count++;
  rateBuckets.set(key, entry);
  return entry.count <= 10;
}
function checkIdempotency(key) {
  for (const [k, v] of idemBuffer) if (Date.now() - v.at >= 60000) idemBuffer.delete(k);
  return idemBuffer.get(key) || null;
}
function authorized(req, context) {
  if (context.mode === 'sandbox' || context.mode === 'synthetic') return true;
  const expected = process.env.JUNTER_BEARER_TOKEN;
  const supplied = String(req.headers?.['x-junter-token'] || req.headers?.authorization || '').replace(/^Bearer\s+/i, '');
  if (!expected || !supplied) return false;
  const a = Buffer.from(expected), b = Buffer.from(supplied);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function syntheticWriteAuthorization(req, env = process.env) {
  // The production URL is a public recruiter demo: it is structurally
  // read-only even if a write secret is accidentally configured there.
  if (env.VERCEL_ENV === 'production') {
    return { ok: false, status: 403, code: 'public_demo_read_only', message: 'public synthetic demo is read-only' };
  }
  // Durable synthetic writes are deployed only to protected Vercel Preview.
  // An exact allowlist keeps development, unset, and unknown environments
  // outside the write path before request validation or store access.
  if (env.VERCEL_ENV !== 'preview') {
    return { ok: false, status: 403, code: 'protected_preview_required', message: 'synthetic writes require protected preview mode' };
  }
  if (env.JUNTER_SYNTHETIC_WRITES_ENABLED !== 'true') {
    return { ok: false, status: 403, code: 'protected_preview_required', message: 'synthetic writes require protected preview mode' };
  }
  const expected = env.JUNTER_SYNTHETIC_WRITE_TOKEN;
  const supplied = String(req.headers?.['x-junter-token'] || req.headers?.authorization || '').replace(/^Bearer\s+/i, '');
  if (!expected || !supplied) return { ok: false, status: 401, code: 'unauthorized', message: 'protected preview authorization required' };
  const a = Buffer.from(expected), b = Buffer.from(supplied);
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return { ok: false, status: 401, code: 'unauthorized', message: 'protected preview authorization required' };
  return { ok: true };
}

function validateSyntheticMutation(body) {
  const details = {};
  // Notes are intentionally never a public/demo mutation. Blocking remains
  // available for action-path verification, but only with its fixed server-side
  // marker rather than a caller-controlled reason.
  if (body.action === 'edit_notes') details.action = 'not available in synthetic storage';
  if (body.action === 'mark_blocked' && Object.hasOwn(body.payload || {}, 'reason')) details['payload.reason'] = 'not available in synthetic storage';
  return details;
}

async function executeSynthetic(req, body) {
  if (req.method !== 'POST') return { status: 405, body: { ok: false, error: { code: 'method_not_allowed', message: 'POST only' } } };
  const access = syntheticWriteAuthorization(req);
  if (!access.ok) return { status: access.status, body: { ok: false, error: { code: access.code, message: access.message } } };
  const details = validate(body);
  if (Object.keys(details).length) return { status: 400, body: { ok: false, error: 'schema validation failed', error_code: 'validation_failed', details } };
  const syntheticDetails = validateSyntheticMutation(body);
  if (Object.keys(syntheticDetails).length) return { status: 400, body: { ok: false, error: 'schema validation failed', error_code: 'validation_failed', details: syntheticDetails } };
  const result = await (await getSyntheticStore()).apply(body);
  return { status: result.status, body: { ok: result.status === 200, role: result.role || null, idempotency_replay: Boolean(result.idempotency_replay), request_id: result.request_id || null, applied_at: result.applied_at || null, ...(result.error ? { error: result.error } : {}) } };
}

async function execute(req, body, request_id, applied_at) {
  const response = (status, error, role = null, extra = {}) => ({ status, body: { ok: status === 200, role, idempotency_replay: false, request_id, applied_at, ...(error ? { error } : {}), ...extra } });
  if (req.method !== 'POST') return response(405, { code: 'method_not_allowed', message: 'POST only' });
  const details = validate(body);
  if (Object.keys(details).length) return response(400, 'schema validation failed', null, { details, error_code: 'validation_failed' });
  const context = storeContext();
  if (!authorized(req, context)) return response(401, { code: 'unauthorized', message: 'bearer token required' });
  const key = `${context.mode}:${context.id || 'mock'}:${body.idempotency_key}`;
  const prior = checkIdempotency(key);
  if (prior) return { status: 200, body: { ...structuredClone(prior.response), idempotency_replay: true } };
  if (!checkRateLimit(`${context.mode}:${req.headers?.['x-forwarded-for'] || 'operator'}`)) return response(429, { code: 'rate_limited', message: 'too many requests' }, null, { retry_after: 60 });
  const read = await readStore(context);
  if (read.error || !read.value || typeof read.value !== 'object') throw new Error('store unavailable');
  const data = read.value;
  const roles = Array.isArray(data.roles) ? data.roles : Array.isArray(data.pipeline) ? data.pipeline : [];
  const idx = roles.findIndex(role => Number(role.id) === body.role_id);
  if (idx < 0) return response(404, { code: 'role_not_found', message: 'role not in store' });
  const updated = applyAction(roles[idx], body.action, body.payload || {});
  if (body.action !== 'view') {
    const nextRoles = roles.slice(); nextRoles[idx] = updated;
    const newData = { ...data, roles: nextRoles, lastUpdated: applied_at };
    if (Array.isArray(data.pipeline)) newData.pipeline = nextRoles;
    const result = await writeStore(newData, read.etag, context);
    if (result.ok) {
      // Read the exact stored role back before claiming success. This checks
      // adapter behavior, not a substitute for distributed atomic CAS.
      const confirmed = await readStore(context);
      const confirmedRoles = confirmed.value?.roles || confirmed.value?.pipeline || [];
      const authoritative = confirmedRoles.find(role => Number(role.id) === body.role_id);
      if (JSON.stringify(authoritative) !== JSON.stringify(updated)) {
        return response(409, { code: 'conflict', message: 'server state is authoritative' }, wire(authoritative));
      }
    }
    if (!result.ok) {
      if (result.code !== 'conflict') return response(503, { code: result.code || 'storage_unavailable', message: 'safe write unavailable' });
      const current = await readStore(context);
      const currentRoles = current.value?.roles || current.value?.pipeline || [];
      return response(409, { code: 'conflict', message: 'server state is authoritative' }, wire(currentRoles.find(role => Number(role.id) === body.role_id)));
    }
  }
  const success = response(200, null, wire(updated));
  idemBuffer.set(key, { at: Date.now(), response: success.body });
  return success;
}

export default async function handler(req, res) {
  // Once a synthetic database is configured, this is the only public write
  // authority. The legacy local seam below remains for offline regression tests.
  if (process.env.JUNTER_MODE === 'synthetic' || process.env.JUNTER_SYNTHETIC_DATABASE_DATABASE_URL) {
    let body = req.body;
    if (typeof body === 'string') { try { body = JSON.parse(body); } catch { body = null; } }
    let result;
    try { result = await executeSynthetic(req, body); }
    catch { result = { status: 503, body: { ok: false, role: null, error: { code: 'persistence_unavailable', message: 'safe persistence unavailable' } } }; }
    res.setHeader('Cache-Control', 'no-store');
    if (result.status === 405) res.setHeader('Allow', 'POST');
    return res.status(result.status).json(result.body);
  }
  // Serialize before the first await: same-instance parallel calls cannot
  // pass the replay check together or overwrite different role updates.
  const previous = queue;
  let release;
  queue = new Promise(resolve => { release = resolve; });
  await previous;
  const request_id = crypto.randomUUID();
  const timestamp = new Date().toISOString();
  let body = req.body;
  if (typeof body === 'string') { try { body = JSON.parse(body); } catch { body = null; } }
  const audit = status => ({ timestamp, ts: timestamp, request_id, action: body?.action ?? null, role_id: body?.role_id ?? null, source: body?.source ?? null, payload: body?.payload ?? null, idempotency_key: body?.idempotency_key ?? null, response_status: status });
  let result;
  try {
    // Preflight before mutation, including on view and malformed attempts.
    // The extra pending record makes inability to write the final record
    // diagnosable; every normal attempt has one final status record as well.
    appendAudit({ ...audit(null), phase: 'attempt' });
    result = await execute(req, body, request_id, timestamp);
    appendAudit({ ...audit(result.status), phase: 'response', idempotency_replay: result.body.idempotency_replay });
  } catch {
    result = { status: 503, body: { ok: false, role: null, idempotency_replay: false, request_id, applied_at: timestamp, error: { code: 'persistence_unavailable', message: 'safe persistence unavailable' } } };
    try { appendAudit({ ...audit(503), phase: 'response' }); } catch { /* Cannot claim a successful audit on unsupported runtime. */ }
  } finally { release(); }
  res.setHeader('Cache-Control', 'no-store');
  if (result.status === 405) res.setHeader('Allow', 'POST');
  if (result.status === 429) res.setHeader('Retry-After', '60');
  return res.status(result.status).json(result.body);
}

export const __test = { validate, applyAction, checkIdempotency, checkRateLimit, syntheticWriteAuthorization, validateSyntheticMutation, VALID_ACTIONS, VALID_GATES, VALID_SOURCES, IDEMPOTENCY_KEY_RE, idemBuffer, rateBuckets, appendAudit };

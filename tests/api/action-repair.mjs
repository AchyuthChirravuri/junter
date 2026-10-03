import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import handler, { __test } from '../../api/action.js';
import { digest, patchEdgeConfig, storeContext, writeStore } from '../../lib/store.js';
import dataHandler from '../../api/data.js';

const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'junter-api-repair-'));
const log = path.join(folder, 'actions.jsonl');
process.env.JUNTER_AUDIT_LOG = log;
let state, writes, conflict, patchCalls;
function reset() {
  __test.idemBuffer.clear(); __test.rateBuckets.clear();
  for (const name of ['VERCEL', 'VERCEL_ENV', 'JUNTER_MODE', 'JUNTER_BEARER_TOKEN', 'JUNTER_SYNTHETIC_WRITE_TOKEN', 'JUNTER_SYNTHETIC_WRITES_ENABLED', 'JUNTER_SANDBOX_CONFIG_ID', 'JUNTER_PERSONAL_CONFIG_ID', 'EDGE_CONFIG', 'JUNTER_VERCEL_API_TOKEN', 'JUNTER_SYNTHETIC_DATABASE_DATABASE_URL', 'JUNTER_SYNTHETIC_DATABASE_NAMESPACE']) delete process.env[name];
  delete globalThis.__junterSyntheticStore;
  process.env.JUNTER_AUDIT_LOG = log;
  state = { roles: [{ id: 1, status: 'pinged', routed: '', angle: 'original', company_research: { application_strategy: { angle: 'original' } } }], lastUpdated: null };
  writes = 0; conflict = false; patchCalls = [];
  globalThis.junterStoreValue = state;
  globalThis.__junterActionStore = async (value, expected, context) => {
    await new Promise(resolve => setTimeout(resolve, 5));
    if (value === undefined) return { value: structuredClone(state), etag: digest(state) };
    if (conflict) { conflict = false; state.roles[0].status = 'packaged'; state.roles[0].routed = 'pkg'; return { ok: false, code: 'conflict' }; }
    if (expected !== digest(state)) return { ok: false, code: 'conflict' };
    writes++; state = structuredClone(value); globalThis.junterStoreValue = state;
    return { ok: true };
  };
}
let serial = 0;
function body(action = 'mark_interested', payload = {}) {
  return { action, role_id: 1, payload, source: 'ui', idempotency_key: `mock-action-key-${String(++serial).padStart(8, '0')}` };
}
async function invoke(value, headers = {}, method = 'POST') {
  const res = { statusCode: 0, headers: {}, status(s) { this.statusCode = s; return this; }, setHeader(k,v) { this.headers[k] = v; }, json(value) { this.body = value; return this; } };
  await handler({ method, body: value, headers }, res);
  return res;
}

test('strict schema and payload failures return exact 400 shape before mutation', async () => {
  reset();
  const invalid = [null, 'not JSON', [], { ...body(), mode: 'personal' }, { ...body(), role_id: '1' }, { ...body(), source: 'email' }, { ...body(), idempotency_key: '' }, { ...body(), payload: null }, body('edit_notes', {}), body('complete_gate', { gate: 'bad' }), body('view', { notes: 'extra' }), { ...body(), client_ts: 'yesterday' }];
  for (const b of invalid) {
    const result = await invoke(b);
    assert.equal(result.statusCode, 400); assert.equal(result.body.error, 'schema validation failed'); assert.ok(Object.keys(result.body.details).length);
  }
  assert.equal(writes, 0);
});
test('all status transitions and shared notes/gates are persisted', async () => {
  reset();
  for (const [action, status, routed] of [['mark_interested','interested','int'], ['mark_packaged','packaged','pkg'], ['mark_submitted','submitted','sub'], ['mark_blocked','blocked','']]) {
    const r = await invoke(body(action)); assert.equal(r.statusCode, 200); assert.equal(r.body.role.status, status); assert.equal(state.roles[0].routed, routed);
  }
  await invoke(body('edit_notes', { notes: 'new angle' }));
  assert.equal(state.roles[0].angle, 'new angle'); assert.equal(state.roles[0].company_research.application_strategy.angle, 'new angle');
  await invoke(body('complete_gate', { gate: 'backgrounder_read' }));
  assert.equal(state.roles[0].gates.backgrounder_read, true); assert.equal(writes, 6);
});
test('view is audit-only: zero writes, byte-identical state', async () => {
  reset(); const original = JSON.stringify(state);
  const r = await invoke(body('view')); assert.equal(r.statusCode, 200); assert.equal(writes, 0); assert.equal(JSON.stringify(state), original);
});
test('unknown role is 404 with no mutation', async () => {
  reset(); const r = await invoke({ ...body('edit_notes', { notes: 'no role' }), role_id: 999 });
  assert.equal(r.statusCode, 404); assert.equal(r.body.error.code, 'role_not_found'); assert.equal(writes, 0);
});
test('actual concurrent same-key calls execute one mutation and replay', async () => {
  reset(); const b = body();
  const results = await Promise.all([invoke(b), invoke(b)]);
  assert.deepEqual(results.map(r => r.statusCode), [200,200]); assert.equal(writes, 1);
  assert.deepEqual(results.map(r => r.body.idempotency_replay), [false,true]);
  assert.equal(results[0].body.request_id, results[1].body.request_id);
  assert.equal(state.roles[0]._actions.length, 1);
});
test('same key becomes fresh after the documented 60-second window', async () => {
  reset(); const b = body(); await invoke(b);
  const entry = [...__test.idemBuffer.values()][0]; entry.at -= 60001;
  const r = await invoke(b); assert.equal(r.body.idempotency_replay, false); assert.equal(writes, 2);
});
test('conflict returns updated authoritative role', async () => {
  reset(); conflict = true;
  const r = await invoke(body('mark_blocked')); assert.equal(r.statusCode, 409); assert.equal(r.body.error.code, 'conflict'); assert.equal(r.body.role.routed, 'pkg'); assert.equal(writes, 0);
});
test('sandbox selection is server-owned, personal requires explicit auth', async () => {
  reset(); assert.equal(storeContext().mode, 'sandbox');
  assert.equal((await invoke({ ...body(), mode: 'personal' })).statusCode, 400);
  process.env.JUNTER_MODE = 'personal'; assert.equal((await invoke(body())).statusCode, 401); assert.equal(writes, 0);
  process.env.JUNTER_MODE = 'sandbox'; process.env.JUNTER_SANDBOX_CONFIG_ID = 'ecfg_mock'; process.env.JUNTER_PERSONAL_CONFIG_ID = 'ecfg_mock';
  assert.equal((await invoke(body())).statusCode, 503); assert.equal(writes, 0);
});
test('missing synthetic configuration makes the public data route fail closed', async () => {
  reset();
  const res = { headers: {}, status(s) { this.statusCode = s; return this; }, setHeader(k,v) { this.headers[k] = v; }, json(value) { this.body = value; } };
  await dataHandler({ method: 'GET' }, res);
  assert.equal(res.statusCode, 503);
  assert.deepEqual(res.body.roles, []);
  assert.equal(res.headers['Cache-Control'], 'no-store');
});
test('production synthetic demo rejects unauthenticated POST before persistence', async () => {
  reset();
  process.env.JUNTER_MODE = 'synthetic';
  process.env.VERCEL_ENV = 'production';
  globalThis.__junterSyntheticStore = { async apply() { throw new Error('must not persist'); } };
  const result = await invoke(body());
  assert.equal(result.statusCode, 403);
  assert.equal(result.body.error.code, 'public_demo_read_only');
});
test('synthetic writes fail closed outside Preview before validation or persistence', async () => {
  for (const environment of ['development', undefined, 'staging']) {
    reset();
    process.env.JUNTER_MODE = 'synthetic';
    if (environment !== undefined) process.env.VERCEL_ENV = environment;
    process.env.JUNTER_SYNTHETIC_WRITES_ENABLED = 'true';
    process.env.JUNTER_SYNTHETIC_WRITE_TOKEN = 'test-only-protected-token';
    let applies = 0;
    globalThis.__junterSyntheticStore = { async apply() { applies++; return { status: 200, role: state.roles[0] }; } };

    const result = await invoke({ invalid: true }, { 'x-junter-token': 'test-only-protected-token' });
    assert.equal(result.statusCode, 403, `environment ${environment ?? 'unset'} must be rejected`);
    assert.equal(result.body.error.code, 'protected_preview_required');
    assert.equal(applies, 0);
  }
});
test('protected preview rejects free-form notes and reasons without persistence', async () => {
  reset();
  process.env.JUNTER_MODE = 'synthetic';
  process.env.VERCEL_ENV = 'preview';
  process.env.JUNTER_SYNTHETIC_WRITES_ENABLED = 'true';
  process.env.JUNTER_SYNTHETIC_WRITE_TOKEN = 'test-only-protected-token';
  let applies = 0;
  globalThis.__junterSyntheticStore = { async apply() { applies++; return { status: 200, role: state.roles[0] }; } };
  const headers = { 'x-junter-token': 'test-only-protected-token' };
  const oversized = 'x'.repeat(10_000);
  for (const request of [body('edit_notes', { notes: oversized }), body('mark_blocked', { reason: oversized })]) {
    const result = await invoke(request, headers);
    assert.equal(result.statusCode, 400);
    assert.equal(result.body.error_code, 'validation_failed');
  }
  assert.equal(applies, 0);
});
test('protected preview can verify a fixed-shape synthetic action', async () => {
  reset();
  process.env.JUNTER_MODE = 'synthetic';
  process.env.VERCEL_ENV = 'preview';
  process.env.JUNTER_SYNTHETIC_WRITES_ENABLED = 'true';
  process.env.JUNTER_SYNTHETIC_WRITE_TOKEN = 'test-only-protected-token';
  let received;
  globalThis.__junterSyntheticStore = { async apply(command) { received = command; return { status: 200, role: state.roles[0] }; } };
  const result = await invoke(body('mark_interested'), { authorization: 'Bearer test-only-protected-token' });
  assert.equal(result.statusCode, 200);
  assert.equal(received.action, 'mark_interested');
});
test('all final audit rows contain requested fields even invalid/method failures', async () => {
  reset(); await invoke(null); await invoke(body(), {}, 'GET');
  const rows = fs.readFileSync(log, 'utf8').trim().split('\n').map(JSON.parse).filter(r => r.phase === 'response');
  for (const r of rows) for (const key of ['timestamp','action','role_id','source','payload','idempotency_key','response_status']) assert.ok(Object.hasOwn(r,key));
  assert.ok(rows.some(r => r.response_status === 400)); assert.ok(rows.some(r => r.response_status === 405));
});
test('real OS flock prevents concurrent append interleaving', async () => {
  const target = path.join(folder, 'parallel.jsonl');
  await Promise.all(Array.from({ length: 12 }, (_, i) => new Promise((resolve,reject) => {
    const child = spawn('python3', ['lib/audit-append.py', target]);
    child.on('error', reject); child.on('close', code => code === 0 ? resolve() : reject(new Error(`helper exited ${code}`)));
    child.stdin.end(JSON.stringify({ i, payload: 'x'.repeat(65536) }));
  })));
  const rows = fs.readFileSync(target,'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(rows.length,12); assert.equal(new Set(rows.map(r => r.i)).size,12); assert.ok(rows.every(r => r.payload.length === 65536));
});
test('Vercel audit failure and uncoordinated production storage fail closed', async () => {
  reset(); process.env.VERCEL = '1'; const r = await invoke(body()); assert.equal(r.statusCode, 503); assert.equal(writes, 0);
  delete process.env.VERCEL; delete globalThis.__junterActionStore;
  assert.equal((await writeStore({},'etag', { mode: 'sandbox', id: 'ecfg_mock' })).code, 'concurrency_unavailable');
});
test.after(() => { fs.rmSync(folder, { recursive: true, force: true }); });

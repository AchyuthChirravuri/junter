// Fixture tests for the /api/data serverless handler.
//
// These run the REAL handler (api/data.js) against the REAL @vercel/edge-config
// SDK, pointed at a local mock of the Edge Config item endpoint via the
// `EDGE_CONFIG` connection string. No Vercel account, no network, no secrets.
//
// Deliberately NOT under api/ — Vercel turns every module in api/ into a public
// route, so the tests live outside it and the deployed surface stays just
// /api/data.
//
// Run:  node --test tests/api/route_test.mjs
//
// Covers the three required read states (populated, missing, failed) plus the
// envelope edge cases the UI relies on (empty string, wrong type, exporter's
// native `pipeline` shape), and asserts the failure body leaks no detail.
import assert from 'node:assert/strict';
import http from 'node:http';
import test, { after, before } from 'node:test';

// --- Mock Edge Config item endpoint -----------------------------------------
// One server for every case; each request is answered from `state`, so the SDK
// can keep a single cached client while we drive 200/404/500 and different
// stored values per assertion.
const state = { mode: 'ok', value: undefined };

const server = http.createServer((req, res) => {
  const path = new URL(req.url, 'http://localhost').pathname;
  // Expect /<id>/item/<key>
  const match = path.match(/^\/[^/]+\/item\/(.+)$/);
  if (!match) {
    res.writeHead(400).end('bad path');
    return;
  }
  if (state.mode === 'fail') {
    res.writeHead(500, { 'content-type': 'application/json' }).end('{"error":"boom"}');
    return;
  }
  if (state.mode === 'missing') {
    // 404 WITH the digest header == "key not present" -> SDK returns undefined.
    res.writeHead(404, { 'x-edge-config-digest': 'd' }).end();
    return;
  }
  res
    .writeHead(200, { 'content-type': 'application/json' })
    .end(JSON.stringify(state.value));
});

let baseUrl;

before(async () => {
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();
  baseUrl = `http://127.0.0.1:${port}/ecfg_test`;
  // The connection string must exist before the first get() call; the SDK
  // initialises its default client lazily from this variable.
  process.env.EDGE_CONFIG = `${baseUrl}?token=test-token`;
  process.env.NODE_ENV = 'production'; // skip the dev-only SWR cache
});

after(() => server.close());

// --- Minimal res double -----------------------------------------------------
function makeRes() {
  return {
    statusCode: null,
    headers: {},
    body: undefined,
    setHeader(k, v) {
      this.headers[k.toLowerCase()] = v;
    },
    status(c) {
      this.statusCode = c;
      return this;
    },
    json(obj) {
      this.body = obj;
      return this;
    },
  };
}

const handler = (await import('../../api/data.js')).default;

async function call() {
  const res = makeRes();
  await handler({ method: 'GET', url: '/api/data', headers: {} }, res);
  return res;
}

const REQUIRED_CACHE = 's-maxage=60, stale-while-revalidate=300';

// --- Populated read ---------------------------------------------------------
test('populated value: returns roles + lastUpdated, cache header set', async () => {
  state.mode = 'ok';
  state.value = {
    roles: [
      { id: 1, company: 'Acme Test Co', role: 'Product Manager', fit_score: 8.1, status: 'interested' },
    ],
    lastUpdated: '2026-10-01T12:00:00-04:00',
  };
  const res = await call();
  assert.equal(res.statusCode, 200);
  assert.equal(res.headers['cache-control'], REQUIRED_CACHE);
  assert.equal(res.body.error, undefined);
  assert.equal(res.body.roles.length, 1);
  assert.equal(res.body.roles[0].company, 'Acme Test Co');
  assert.equal(res.body.lastUpdated, '2026-10-01T12:00:00-04:00');
});

test('exporter-native shape: pipeline promoted to roles, lastUpdated defaulted', async () => {
  state.mode = 'ok';
  state.value = {
    snapshot_kind: 'real',
    snapshot_at: '2026-10-01T12:00:00-04:00',
    pipeline: [{ id: 7, company: 'Beta Fixture', role: 'PMM', fit_score: 6.5, status: 'packaged' }],
    deadline_rail: [],
  };
  const res = await call();
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.roles.length, 1);
  assert.equal(res.body.roles[0].company, 'Beta Fixture');
  assert.equal(res.body.lastUpdated, null);
  assert.equal(res.body.snapshot_kind, 'real'); // sibling sections preserved
});

test('extra sections pass through untouched', async () => {
  state.mode = 'ok';
  state.value = {
    roles: [{ id: 1 }],
    lastUpdated: 'x',
    deadline_rail: [{ id: 1, days_out: 3 }],
    role_detail: { '1': { company_summary: 's' } },
  };
  const res = await call();
  assert.deepEqual(res.body.deadline_rail, [{ id: 1, days_out: 3 }]);
  assert.deepEqual(res.body.role_detail, { '1': { company_summary: 's' } });
});

// --- Missing / empty reads --------------------------------------------------
test('missing key: empty envelope, no error field, still 200', async () => {
  state.mode = 'missing';
  const res = await call();
  assert.equal(res.statusCode, 200);
  assert.deepEqual(res.body, { roles: [], lastUpdated: null });
  assert.equal(res.headers['cache-control'], REQUIRED_CACHE);
});

test('empty string value: empty envelope, no error field', async () => {
  state.mode = 'ok';
  state.value = '';
  const res = await call();
  assert.equal(res.statusCode, 200);
  assert.deepEqual(res.body, { roles: [], lastUpdated: null });
  assert.equal(res.body.error, undefined);
});

test('wrong type (array) value: empty envelope, no error field', async () => {
  state.mode = 'ok';
  state.value = [1, 2, 3];
  const res = await call();
  assert.equal(res.statusCode, 200);
  assert.deepEqual(res.body, { roles: [], lastUpdated: null });
});

test('object without roles/pipeline: empty roles, siblings kept', async () => {
  state.mode = 'ok';
  state.value = { snapshot_kind: 'real' };
  const res = await call();
  assert.equal(res.statusCode, 200);
  assert.deepEqual(res.body.roles, []);
  assert.equal(res.body.snapshot_kind, 'real');
  assert.equal(res.body.lastUpdated, null);
});

// --- Failed read ------------------------------------------------------------
test('read failure: error envelope, 200, no leaked detail', async () => {
  state.mode = 'fail';
  const res = await call();
  assert.equal(res.statusCode, 200);
  assert.deepEqual(res.body, {
    roles: [],
    lastUpdated: null,
    error: 'edge-config unavailable',
  });
  // No internal detail may leak: not the token, host, port, or a stack message.
  const serialized = JSON.stringify(res.body);
  for (const leak of ['test-token', '127.0.0.1', String(new URL(baseUrl).port), 'Error', 'boom', 'Bearer']) {
    assert.equal(serialized.includes(leak), false, `leaked "${leak}"`);
  }
});

// --- Invariants -------------------------------------------------------------
test('handler never returns a 5xx in any state', async () => {
  for (const mode of ['ok', 'missing', 'fail']) {
    state.mode = mode;
    state.value = { roles: [{ id: 1 }], lastUpdated: null };
    const res = await call();
    assert.ok(res.statusCode < 500, `mode ${mode} produced ${res.statusCode}`);
  }
});

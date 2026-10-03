// Contract tests for GET /api/data after the synthetic transactional migration.
// They run offline through a process-global test seam; production requires the
// server-only Neon URL and has no Edge Config, fixture, or filesystem fallback.
import assert from 'node:assert/strict';
import test from 'node:test';
import handler from '../../api/data.js';

function makeResponse() {
  return {
    statusCode: null, headers: {}, body: undefined,
    setHeader(key, value) { this.headers[key.toLowerCase()] = value; },
    status(code) { this.statusCode = code; return this; },
    json(value) { this.body = value; return this; },
  };
}

async function call(method = 'GET') {
  const res = makeResponse();
  await handler({ method }, res);
  return res;
}

test('GET reads the configured authoritative transactional store', async () => {
  globalThis.__junterSyntheticStore = {
    async read() { return { roles: [{ id: 1, company: 'Example Co', routed: 'int' }], lastUpdated: '2026-10-03T00:00:00.000Z' }; },
  };
  const res = await call();
  assert.equal(res.statusCode, 200);
  assert.equal(res.headers['cache-control'], 'no-store');
  assert.equal(res.body.roles[0].routed, 'int');
  delete globalThis.__junterSyntheticStore;
});

test('missing configuration fails closed without a legacy-store fallback', async () => {
  delete globalThis.__junterSyntheticStore;
  const original = process.env.JUNTER_SYNTHETIC_DATABASE_DATABASE_URL;
  delete process.env.JUNTER_SYNTHETIC_DATABASE_DATABASE_URL;
  const res = await call();
  assert.equal(res.statusCode, 503);
  assert.deepEqual(res.body.roles, []);
  assert.equal(res.headers['cache-control'], 'no-store');
  if (original === undefined) delete process.env.JUNTER_SYNTHETIC_DATABASE_DATABASE_URL;
  else process.env.JUNTER_SYNTHETIC_DATABASE_DATABASE_URL = original;
});

test('non-GET methods are rejected before storage access', async () => {
  const res = await call('POST');
  assert.equal(res.statusCode, 405);
  assert.equal(res.headers.allow, 'GET');
});

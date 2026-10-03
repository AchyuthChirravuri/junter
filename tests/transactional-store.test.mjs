// Contract tests for the synthetic transactional storage boundary.
// These tests never connect to Neon. They exercise independent store clients
// against one fake transactional database, which is the cross-instance shape
// the public handler relies on.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createTransactionalStore, configurationError } from '../lib/transactional-store.js';

function fixture() {
  return { roles: [{ id: 1, status: 'blocked', routed: '', angle: 'original' }], lastUpdated: null };
}

function fakeDatabase(seed = fixture()) {
  const state = { data: structuredClone(seed), idempotency: new Map(), audit: [], tail: Promise.resolve() };
  return {
    state,
    client() {
      return {
        async transaction(work) {
          // A real adapter provides a DB transaction. The fake serializes its
          // transaction callback so tests model a shared authoritative store,
          // not a process-local mutex.
          const prior = state.tail;
          let release;
          state.tail = new Promise(resolve => { release = resolve; });
          await prior;
          try {
            return await work({
            async getIdempotency(key) { return state.idempotency.get(key) || null; },
            async getRoleForUpdate(roleId) {
              const role = state.data.roles.find(item => item.id === roleId);
              return role ? structuredClone(role) : null;
            },
            async updateRole(role) {
              state.data.roles = state.data.roles.map(item => item.id === role.id ? structuredClone(role) : item);
              state.data.lastUpdated = new Date().toISOString();
            },
            async appendAudit(event) { state.audit.push(structuredClone(event)); },
            async recordIdempotency(key, fingerprint, result) {
              state.idempotency.set(key, { fingerprint, result: structuredClone(result) });
            },
            async readData() { return structuredClone(state.data); },
            async readAudit() { return structuredClone(state.audit); },
          });
          } finally { release(); }
        },
      };
    },
  };
}

function appendAuditRaceDatabase(seed = fixture()) {
  const state = { data: structuredClone(seed), idempotency: new Map(), audit: [] };
  let arrived = 0;
  let releaseReads;
  const readsReady = new Promise(resolve => { releaseReads = resolve; });
  return {
    state,
    client() {
      return {
        async lookupIdempotency(key) { return state.idempotency.get(key) || null; },
        async transaction(work) {
          const staged = { data: structuredClone(state.data), audit: [] };
          return work({
            async getIdempotency() {
              // Both database transactions miss an absent key before either commits.
              arrived++;
              if (arrived === 2) releaseReads();
              await readsReady;
              return null;
            },
            async getRoleForUpdate(roleId) {
              const role = staged.data.roles.find(item => item.id === roleId);
              return role ? structuredClone(role) : null;
            },
            async updateRole(role) {
              staged.data.roles = staged.data.roles.map(item => item.id === role.id ? structuredClone(role) : item);
            },
            async appendAudit(event) {
              // The old audit-first ordering sends the loser to this unique index.
              if (state.audit.some(item => item.idempotency_key === event.idempotency_key)) {
                const error = new Error('duplicate audit idempotency key');
                error.code = '23505';
                throw error;
              }
              state.audit.push(structuredClone(event));
            },
            async recordIdempotency(key, fingerprint, result) {
              if (state.idempotency.has(key)) {
                // Mirror NeonTransactionClient: this is the existing durable
                // idempotency-race conversion seam, unlike appendAudit above.
                const error = new Error('idempotency key won by concurrent transaction');
                error.code = 'JUNTER_IDEMPOTENCY_RACE';
                throw error;
              }
              state.data = structuredClone(staged.data);
              state.audit.push(...structuredClone(staged.audit));
              state.idempotency.set(key, { fingerprint, result: structuredClone(result) });
            },
            async readData() { return structuredClone(state.data); },
            async readAudit() { return structuredClone(state.audit); },
          });
        },
      };
    },
  };
}

const command = (key, action = 'mark_interested') => ({
  action, role_id: 1, payload: {}, source: 'ui', idempotency_key: key,
});

test('independent clients replay the same durable result exactly once', async () => {
  const db = fakeDatabase();
  const firstClient = createTransactionalStore(db.client());
  const secondClient = createTransactionalStore(db.client());
  const [first, replay] = await Promise.all([
    firstClient.apply(command('independent-client-key-0001')),
    secondClient.apply(command('independent-client-key-0001')),
  ]);
  assert.equal(first.status, 200);
  assert.equal(replay.status, 200);
  assert.equal(first.idempotency_replay || replay.idempotency_replay, true);
  assert.equal(db.state.audit.length, 1);
  assert.equal(db.state.data.roles[0].routed, 'int');
});

test('same-key concurrent first use replays when the old audit-first path would hit 23505', async () => {
  const db = appendAuditRaceDatabase();
  const first = createTransactionalStore(db.client());
  const second = createTransactionalStore(db.client());
  const results = await Promise.all([
    first.apply(command('append-audit-race-key-0001')),
    second.apply(command('append-audit-race-key-0001')),
  ]);
  assert.deepEqual(results.map(result => result.status), [200, 200]);
  assert.equal(results.filter(result => result.idempotency_replay).length, 1);
  assert.equal(db.state.audit.length, 1);
  assert.equal(db.state.data.roles[0].routed, 'int');
});

test('an audit failure rolls back the role update and idempotency claim', async () => {
  const state = { data: fixture(), idempotency: new Map(), audit: [] };
  const client = {
    async transaction(work) {
      const staged = { data: structuredClone(state.data), idempotency: new Map(state.idempotency) };
      const result = await work({
        async getIdempotency(key) { return staged.idempotency.get(key) || null; },
        async getRoleForUpdate(roleId) { return structuredClone(staged.data.roles.find(role => role.id === roleId)); },
        async updateRole(role) { staged.data.roles[0] = structuredClone(role); },
        async recordIdempotency(key, fingerprint, response) { staged.idempotency.set(key, { fingerprint, result: structuredClone(response) }); },
        async appendAudit() { throw new Error('audit unavailable'); },
        async readData() { return structuredClone(state.data); },
        async readAudit() { return structuredClone(state.audit); },
      });
      state.data = staged.data;
      state.idempotency = staged.idempotency;
      return result;
    },
  };
  const store = createTransactionalStore(client);
  await assert.rejects(store.apply(command('audit-failure-rollback-01')));
  assert.equal(state.data.roles[0].routed, '');
  assert.equal(state.idempotency.size, 0);
  assert.equal(state.audit.length, 0);
});

test('same idempotency key with a different request is rejected durably', async () => {
  const db = fakeDatabase();
  const store = createTransactionalStore(db.client());
  await store.apply(command('conflicting-key-00000001'));
  const conflict = await store.apply(command('conflicting-key-00000001', 'mark_packaged'));
  assert.equal(conflict.status, 409);
  assert.equal(conflict.error.code, 'idempotency_conflict');
  assert.equal(db.state.audit.length, 1);
});

test('concurrent writes commit state and audit atomically', async () => {
  const db = fakeDatabase();
  const a = createTransactionalStore(db.client());
  const b = createTransactionalStore(db.client());
  const [one, two] = await Promise.all([
    a.apply(command('concurrent-write-key-00001', 'mark_packaged')),
    b.apply(command('concurrent-write-key-00002', 'mark_submitted')),
  ]);
  assert.deepEqual([one.status, two.status], [200, 200]);
  assert.equal(db.state.audit.length, 2);
  assert.equal(db.state.data.roles[0].routed, 'sub');
});

test('audit and idempotency survive store client recreation', async () => {
  const db = fakeDatabase();
  const first = createTransactionalStore(db.client());
  const original = await first.apply(command('recreation-key-000000001'));
  const recreated = createTransactionalStore(db.client());
  const replay = await recreated.apply(command('recreation-key-000000001'));
  assert.equal(replay.idempotency_replay, true);
  assert.equal(replay.request_id, original.request_id);
  assert.equal((await recreated.readAudit()).length, 1);
});

test('missing configuration fails closed before any public mutation', () => {
  assert.match(configurationError({}).message, /JUNTER_SYNTHETIC_DATABASE_DATABASE_URL/);
});

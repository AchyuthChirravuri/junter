// Synthetic-only transactional storage boundary.
// The public routes use this module only when an integration-managed Neon URL is
// configured. There is no Edge Config, filesystem, or process-memory fallback.
import crypto from 'node:crypto';

const URL_KEY = 'JUNTER_SYNTHETIC_DATABASE_DATABASE_URL';
const NAMESPACE_KEY = 'JUNTER_SYNTHETIC_DATABASE_NAMESPACE';
const NAME_RE = /^[a-z][a-z0-9_]{0,62}$/;

export function configurationError(env = process.env) {
  const url = env[URL_KEY];
  if (typeof url !== 'string' || !/^postgres(?:ql)?:\/\//.test(url)) {
    return new Error(`${URL_KEY} is required for synthetic transactional storage`);
  }
  const namespace = env[NAMESPACE_KEY] || 'junter_synthetic';
  if (!NAME_RE.test(namespace)) return new Error(`${NAMESPACE_KEY} is invalid`);
  return null;
}

export function syntheticContext(env = process.env) {
  const error = configurationError(env);
  if (error) throw error;
  return { mode: 'synthetic', namespace: env[NAMESPACE_KEY] || 'junter_synthetic' };
}

const fingerprint = command => crypto.createHash('sha256').update(JSON.stringify({
  action: command.action, role_id: command.role_id, payload: command.payload || {}, source: command.source,
})).digest('hex');

export function applyAction(role, action, payload = {}, now = new Date().toISOString()) {
  const next = structuredClone(role);
  if (action === 'view') return next;
  const statuses = { mark_interested: ['interested', 'int'], mark_packaged: ['packaged', 'pkg'], mark_submitted: ['submitted', 'sub'], mark_blocked: ['blocked', ''] };
  if (statuses[action]) {
    [next.status, next.routed] = statuses[action];
    next.status_date = now.slice(0, 10);
    next.blocked_reason = action === 'mark_blocked' ? (payload.reason || 'user-marked') : '';
  }
  if (action === 'edit_notes') {
    next.angle = payload.notes;
    if (next.company_research?.application_strategy) next.company_research.application_strategy.angle = payload.notes;
  }
  if (action === 'complete_gate') next.gates = { ...(next.gates || {}), [payload.gate]: true };
  return next;
}

function publicRole(role) {
  const copy = structuredClone(role);
  delete copy._actions;
  return copy;
}

// Client protocol deliberately contains only transaction-scoped operations.
// The Neon adapter implements this protocol with BEGIN/COMMIT and row locks;
// unit tests use the same protocol against one shared fake database.
export function createTransactionalStore(client) {
  if (!client || typeof client.transaction !== 'function') throw new Error('transactional client required');
  return {
    async read() { return client.transaction(tx => tx.readData()); },
    async readAudit() { return client.transaction(tx => tx.readAudit()); },
    async apply(command) {
      const requestFingerprint = fingerprint(command);
      try { return await client.transaction(async tx => {
        const previous = await tx.getIdempotency(command.idempotency_key);
        if (previous) {
          if (previous.fingerprint !== requestFingerprint) return { status: 409, error: { code: 'idempotency_conflict', message: 'idempotency key was used for a different request' } };
          return { ...structuredClone(previous.result), idempotency_replay: true };
        }
        const role = await tx.getRoleForUpdate(command.role_id);
        if (!role) return { status: 404, error: { code: 'role_not_found', message: 'role not in store' } };
        const now = new Date().toISOString();
        const updated = applyAction(role, command.action, command.payload || {}, now);
        const result = {
          status: 200, role: publicRole(updated), request_id: crypto.randomUUID(), applied_at: now, idempotency_replay: false,
        };
        if (command.action !== 'view') await tx.updateRole(updated);
        await tx.appendAudit({ ...command, request_id: result.request_id, applied_at: now, response_status: 200 });
        await tx.recordIdempotency(command.idempotency_key, requestFingerprint, result);
        return result;
      });
      } catch (error) {
        if (error?.code !== 'JUNTER_IDEMPOTENCY_RACE' || typeof client.lookupIdempotency !== 'function') throw error;
        const persisted = await client.lookupIdempotency(command.idempotency_key);
        if (!persisted) throw error;
        if (persisted.fingerprint !== requestFingerprint) return { status: 409, error: { code: 'idempotency_conflict', message: 'idempotency key was used for a different request' } };
        return { ...structuredClone(persisted.result), idempotency_replay: true };
      }
    },
  };
}

class NeonTransactionClient {
  constructor(pool, namespace) { this.pool = pool; this.namespace = namespace; }
  async transaction(work) {
    const connection = await this.pool.connect();
    try {
      await connection.query('BEGIN');
      const tx = this.transactionMethods(connection);
      const result = await work(tx);
      await connection.query('COMMIT');
      return result;
    } catch (error) {
      try { await connection.query('ROLLBACK'); } catch { /* original error wins */ }
      throw error;
    } finally { connection.release(); }
  }
  table(name) { return `"${this.namespace}"."${name}"`; }
  async lookupIdempotency(key) {
    const { rows } = await this.pool.query(`SELECT fingerprint, response FROM ${this.table('idempotency')} WHERE idempotency_key = $1`, [key]);
    return rows[0] ? { fingerprint: rows[0].fingerprint, result: rows[0].response } : null;
  }
  transactionMethods(connection) {
    const roles = this.table('roles');
    const idempotency = this.table('idempotency');
    const audit = this.table('audit_events');
    return {
      async getIdempotency(key) {
        const { rows } = await connection.query(`SELECT fingerprint, response FROM ${idempotency} WHERE idempotency_key = $1 FOR UPDATE`, [key]);
        return rows[0] ? { fingerprint: rows[0].fingerprint, result: rows[0].response } : null;
      },
      async getRoleForUpdate(roleId) {
        const { rows } = await connection.query(`SELECT payload FROM ${roles} WHERE role_id = $1 FOR UPDATE`, [roleId]);
        return rows[0]?.payload || null;
      },
      async updateRole(role) { await connection.query(`UPDATE ${roles} SET payload = $2::jsonb, updated_at = NOW() WHERE role_id = $1`, [role.id, JSON.stringify(role)]); },
      async appendAudit(event) { await connection.query(`INSERT INTO ${audit} (request_id, role_id, action, source, payload, idempotency_key, response_status) VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7)`, [event.request_id, event.role_id, event.action, event.source, JSON.stringify(event.payload || {}), event.idempotency_key, event.response_status]); },
      async recordIdempotency(key, keyFingerprint, result) {
        try {
          await connection.query(`INSERT INTO ${idempotency} (idempotency_key, fingerprint, response) VALUES ($1,$2,$3::jsonb)`, [key, keyFingerprint, JSON.stringify(result)]);
        } catch (error) {
          // SELECT ... FOR UPDATE cannot lock a row which does not exist yet.
          // A concurrent first use of this key instead reaches the unique index.
          // Roll back every earlier mutation/audit write, then read the winner.
          if (error?.code === '23505') {
            const race = new Error('idempotency key won by concurrent transaction');
            race.code = 'JUNTER_IDEMPOTENCY_RACE';
            throw race;
          }
          throw error;
        }
      },
      async readData() {
        const { rows } = await connection.query(`SELECT payload FROM ${roles} ORDER BY role_id`);
        return { roles: rows.map(row => row.payload), lastUpdated: null };
      },
      async readAudit() { const { rows } = await connection.query(`SELECT * FROM ${audit} ORDER BY audit_id`); return rows; },
    };
  }
}

let cachedStore;
export async function getSyntheticStore(env = process.env) {
  // Test-only injection keeps route tests offline. Vercel cannot populate this
  // process-global value through an HTTP request, and production still requires
  // the server-only database URL below.
  if (globalThis.__junterSyntheticStore) return globalThis.__junterSyntheticStore;
  if (cachedStore) return cachedStore;
  const context = syntheticContext(env);
  const { Pool } = await import('@neondatabase/serverless');
  const pool = new Pool({ connectionString: env[URL_KEY] });
  cachedStore = createTransactionalStore(new NeonTransactionClient(pool, context.namespace));
  return cachedStore;
}

export const __test = { fingerprint, NAME_RE, URL_KEY, NAMESPACE_KEY };

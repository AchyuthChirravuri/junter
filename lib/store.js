// Server-only storage. The Edge Config SDK is a reader, not a write API.
// See docs/action-api-contract.md for the unresolved distributed CAS gate.
import { get } from '@vercel/edge-config';
import crypto from 'node:crypto';

export const digest = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');

export function storeContext() {
  const mode = process.env.JUNTER_MODE || 'sandbox';
  if (!['sandbox', 'personal'].includes(mode)) throw new Error('invalid server mode');
  const id = process.env[mode === 'sandbox' ? 'JUNTER_SANDBOX_CONFIG_ID' : 'JUNTER_PERSONAL_CONFIG_ID'];
  if (mode === 'sandbox' && id && id === process.env.JUNTER_PERSONAL_CONFIG_ID) {
    throw new Error('sandbox and personal stores must differ');
  }
  // GET /api/data uses EDGE_CONFIG, so it must point at this exact store.
  if (id && process.env.EDGE_CONFIG) {
    const configured = new URL(process.env.EDGE_CONFIG).pathname.split('/').filter(Boolean)[0];
    if (configured !== id) throw new Error('read/write store mismatch');
  }
  return { mode, id };
}

export async function readStore(context = storeContext()) {
  if (typeof globalThis.__junterActionStore === 'function') {
    return globalThis.__junterActionStore(undefined, undefined, context);
  }
  if (!context.id || !process.env.EDGE_CONFIG) throw new Error('store not configured');
  const value = await get('junter-data');
  if (!value || typeof value !== 'object') throw new Error('store unavailable');
  return { value, etag: digest(value) };
}

// Actual REST update shape from https://openapi.vercel.sh. Exported so the
// wire path can be exercised with fetch mocks without credentials/network.
// It is NOT an atomic compare-and-swap: never call it as a concurrency guard.
export async function patchEdgeConfig(value, context, fetcher = fetch) {
  const token = process.env.JUNTER_VERCEL_API_TOKEN;
  if (!token || !/^ecfg_[A-Za-z0-9_-]+$/.test(context.id || '')) throw new Error('write configuration missing');
  const url = new URL(`https://api.vercel.com/v1/global-config/${context.id}/items`);
  if (process.env.JUNTER_VERCEL_TEAM_ID) url.searchParams.set('teamId', process.env.JUNTER_VERCEL_TEAM_ID);
  const response = await fetcher(url.toString(), {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ items: [{ operation: 'upsert', key: 'junter-data', value }] }),
  });
  if ([409, 412].includes(response.status)) return { ok: false, code: 'conflict' };
  if (!response.ok) throw new Error('edge config update failed');
  return { ok: true };
}

export async function writeStore(value, expectedEtag, context = storeContext()) {
  if (typeof globalThis.__junterActionStore === 'function') {
    return globalThis.__junterActionStore(value, expectedEtag, context);
  }
  // A process mutex cannot protect this full-item update from other Vercel
  // instances or the CSV publisher. No documented CAS parameter was found in
  // the current REST OpenAPI. Refuse rather than claim atomic concurrency.
  return { ok: false, code: 'concurrency_unavailable' };
}

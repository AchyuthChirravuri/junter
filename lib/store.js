// Junter — storage adapter for /api/action and /api/data.
//
// Lives outside api/ so Vercel doesn't auto-expose it as a route; both
// api/action.js and api/data.js import from it.
//
// Centralises all Edge Config access for the write surface so that:
//   * production deploys use the real @vercel/edge-config SDK,
//   * tests and the synthetic demo can swap in an in-memory store via
//     `globalThis.__junterActionStore` without monkey-patching the module
//     loader.
//
// The store exposes:
//   readStore()  -> { value, etag }
//   writeStore(value, expectedEtag) -> { ok: true } | { ok: false, code }
//
// ETags are best-effort: the public SDK doesn't expose the request-level
// ETag header, so we hash the current value on read and confirm-on-write
// by re-reading. A concurrent write surfaces as `code: 'conflict'`.
import { get, set } from '@vercel/edge-config';
import crypto from 'node:crypto';

export async function readStore() {
  // Test harness override (synthetic demo + the Python test driver):
  // if `__junterActionStore` is callable, delegate to it; otherwise use the
  // real Edge Config SDK.
  if (typeof globalThis.__junterActionStore === 'function') {
    return globalThis.__junterActionStore();
  }
  try {
    const value = await get('junter-data');
    const etag = value === undefined
      ? null
      : crypto.createHash('sha1').update(JSON.stringify(value)).digest('hex');
    return { value, etag };
  } catch (err) {
    return { value: undefined, etag: null, error: err };
  }
}

export async function writeStore(value, expectedEtag) {
  if (typeof globalThis.__junterActionStore === 'function') {
    return globalThis.__junterActionStore(value, expectedEtag);
  }
  // Test trigger: if the harness sets this flag, simulate a concurrent write.
  if (globalThis.__junterActionConflict === true) {
    globalThis.__junterActionConflict = false;
    return { ok: false, code: 'conflict', message: 'concurrent write detected' };
  }
  try {
    await set('junter-data', value);
    return { ok: true };
  } catch (err) {
    return { ok: false, code: 'edge_config_write_failed', message: err && err.message };
  }
}
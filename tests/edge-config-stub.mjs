// In-memory replacement for @vercel/edge-config used in tests.
// State lives on globalThis so the Python harness can mutate it between calls.
const storeKey = 'junterStoreValue';

export async function get(key) {
  if (key !== 'junter-data') return undefined;
  const v = globalThis[storeKey];
  return v === undefined ? undefined : JSON.parse(JSON.stringify(v));
}
export async function set(key, value) {
  if (key !== 'junter-data') throw new Error('unknown key: ' + key);
  if (globalThis.__junterActionConflict === true) {
    globalThis.__junterActionConflict = false;
    throw new Error('conflict');
  }
  globalThis[storeKey] = JSON.parse(JSON.stringify(value));
}
export async function digest(value) {
  if (value === undefined) return null;
  // Cheap deterministic hash without pulling crypto in.
  return 'd-' + JSON.stringify(value).length;
}
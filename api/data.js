// Junter — Vercel serverless function serving live tracker JSON from Edge Config.
//
// Contract (shared by this route, the UI loader, and the local publisher):
//   HTTP 200, JSON body { roles: [...], lastUpdated: <ISO string | null>, ... }
//   `roles[]` entries are role objects in the tracker's published schema
//   (id, company, role, fit_score, source, url, status, deadline,
//    blocked_reason, ...). Any sibling sections the publisher stores
//    (deadline_rail, role_detail, run_health, ...) pass through untouched so the
//    UI can render them.
//
// Degradation — this handler never returns 5xx:
//   * key absent / empty / wrong type -> { roles: [], lastUpdated: null }
//   * Edge Config unreachable         -> { roles: [], lastUpdated: null,
//                                          error: 'edge-config unavailable' }
//   The catch branch never echoes the exception message, so no internal detail
//   (connection string, stack, host) leaks to the client.
//
// Cache + auth: exactly the specified edge-cache posture
// ('s-maxage=60, stale-while-revalidate=300') on the response path; no other
// caching directive and no authentication. The item key is `junter-data`.
//
// Requires "type": "module" in the project's package.json (ESM handler) and
// @vercel/edge-config as a dependency so the function bundles.
import { get } from '@vercel/edge-config';

const EMPTY = { roles: [], lastUpdated: null };
const CACHE_CONTROL = 's-maxage=60, stale-while-revalidate=300';

// Guarantee the agreed envelope for whatever the store holds, without dropping
// any sibling section. Idempotent: a well-formed stored value comes back
// unchanged apart from an added `lastUpdated: null` when it is missing.
//   - object with a roles[] array  -> kept as-is (+ lastUpdated default)
//   - object with the exporter's native `pipeline` array (no roles) -> exposed
//     under `roles` rather than silently dropped
//   - anything else (null, "", [], scalar) -> the empty envelope
function envelope(value) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const shaped = Object.assign({}, value);
    if (!Array.isArray(shaped.roles)) {
      shaped.roles = Array.isArray(shaped.pipeline) ? shaped.pipeline : [];
    }
    if (!('lastUpdated' in shaped)) shaped.lastUpdated = null;
    return shaped;
  }
  return Object.assign({}, EMPTY);
}

export default async function handler(req, res) {
  try {
    const data = await get('junter-data');
    res.setHeader('Cache-Control', CACHE_CONTROL);
    res.status(200).json(envelope(data));
  } catch (err) {
    // Unset EDGE_CONFIG, an invalid connection string, or a network blip:
    // still HTTP 200 with a well-formed empty body. The UI treats an empty
    // roles[] the same as "API unavailable" and falls back to its embedded seed.
    res.status(200).json(Object.assign({}, EMPTY, { error: 'edge-config unavailable' }));
  }
}

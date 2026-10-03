// GET /api/data — synthetic transactional state only.
// There is intentionally no Edge Config or embedded-data fallback on this route:
// a configured public action path must read the same authoritative database.
import { getSyntheticStore } from '../lib/transactional-store.js';

const EMPTY = { roles: [], lastUpdated: null };

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return res.status(405).json({ ok: false, error: { code: 'method_not_allowed', message: 'GET only' } });
  }
  try {
    const data = await (await getSyntheticStore()).read();
    res.setHeader('Cache-Control', 'no-store');
    return res.status(200).json({ ...data, roles: Array.isArray(data.roles) ? data.roles : [] });
  } catch {
    // Fail closed: do not quietly return an old shared store or UI fixture.
    res.setHeader('Cache-Control', 'no-store');
    return res.status(503).json({ ...EMPTY, error: 'synthetic transactional storage unavailable' });
  }
}

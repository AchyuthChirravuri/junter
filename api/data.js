// Junter — Vercel serverless function serving live tracker JSON from Vercel Edge Config.
//
// Contract: returns, verbatim, the JSON value stored in Edge Config under the
// `junter-data` item key. That value is the snapshot produced by
// snapshot-export/export.py and pushed by the local-only scripts/push-data.py.
// The UI maps the exporter's shape onto its own state (see ui/app.js).
//
// Never 500s: an empty store or an unreachable Edge Config degrades to a
// well-formed empty payload so the UI can fall back to its embedded seed.
//
// Cache: matches Vercel's default edge caching posture (no extra layer added).
import { get } from '@vercel/edge-config';

const EMPTY = { roles: [], lastUpdated: null };

export default async function handler(req, res) {
  try {
    const data = await get('junter-data');
    res.setHeader('Cache-Control', 's-maxage=60, stale-while-revalidate=300');
    res.status(200).json(data || EMPTY);
  } catch (err) {
    // Edge Config unset / network blip: still 200 with an empty, well-formed body.
    // The UI treats an empty roles[] the same as "API unavailable" and uses its seed.
    res.setHeader('Cache-Control', 'no-store');
    res.status(200).json({
      roles: [],
      lastUpdated: null,
      error: 'edge-config unavailable',
    });
  }
}

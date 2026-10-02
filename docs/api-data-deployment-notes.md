# `/api/data` — deployment notes

Handoff for the integration worker (card: *Configure Vercel, publish live data,
and verify the deployed board*). Everything here is either documented behavior
with a citation, or a check that must be run once `api/data.js` is on the
deployed branch.

## What this route is

- `api/data.js` at the **repository root** — one Vercel Function, served at
  `/api/data`.
- Reads the `junter-data` Edge Config item and returns it inside the shared
  envelope `{ roles: [...], lastUpdated: <ISO | null>, ... }`.
- Success and empty/failed reads are **always HTTP 200** (never 5xx). A read
  failure returns `{ roles: [], lastUpdated: null, error: 'edge-config unavailable' }`
  and never echoes the exception.
- Response carries exactly one cache directive:
  `Cache-Control: s-maxage=60, stale-while-revalidate=300`. No other caching
  layer, no authentication.
- Requires `"type": "module"` (already set in `package.json`) and
  `@vercel/edge-config` (already a dependency).

## Coexistence with the `ui/` static deployment

Vercel discovers Functions from an **`api` directory at the project root**,
independently of where static files are served from. The static side is governed
separately by the Output Directory setting.

> "For all officially supported runtimes, the only requirement is to create an
> `api` directory at the root of your project directory, placing your Vercel
> functions inside." — Vercel docs, *vercel.json → functions*

> "Only the contents of this Output Directory will be served statically by
> Vercel." — Vercel docs, *Configuring a Build → Output Directory*

So the two live side by side:

| Source | Served at |
| --- | --- |
| `ui/` (project Output Directory) | `/`, `/styles.css`, `/app.js`, … |
| `api/data.js` (root `api/`) | `/api/data` |

**Observed on the current production deployment** (`junter-xi.vercel.app`,
commit `6e62d00`, i.e. before `api/` existed):

- `GET /` → HTTP 200, `text/html` — the `ui/index.html` prototype (confirms the
  `ui/` Output Directory is in effect).
- `GET /api/data` → HTTP 404 — expected, because `main` has no `api/` yet.

## Required checks on the first deploy that contains `api/`

1. `curl -s https://<deployment-url>/api/data` → **exactly**
   `{"roles":[],"lastUpdated":null,"error":"edge-config unavailable"}`
   with HTTP 200 until the store is populated (verifies the function is routed
   and degrades safely when `EDGE_CONFIG` is unset).
2. `curl -sI https://<deployment-url>/api/data` → HTTP 200 and
   `cache-control: s-maxage=60, stale-while-revalidate=300`.
3. `curl -s https://<deployment-url>/` → still the `ui/` prototype (HTTP 200,
   `text/html`). The static site must not regress.
4. After publishing real data, `curl -s .../api/data | python3 -c 'import sys,json; print(len(json.load(sys.stdin)["roles"]))'`
   → `> 0`.

If (1) 404s instead of reaching the function, the root `api/` was not picked up;
the fix is to add a root `vercel.json` making the discovery explicit — but only
after reproducing, since the current production deployment must not regress:

```json
{ "$schema": "https://openapi.vercel.sh/vercel.json",
  "outputDirectory": "ui",
  "functions": { "api/data.js": { "runtime": "nodejs22.x" } } }
```

*(Do not add this pre-emptively — it is unverified and the documented
zero-config layout should work as-is.)*

## Environment variables the function needs

| Name | Purpose | Where |
| --- | --- | --- |
| `EDGE_CONFIG` | Edge Config **read** connection string | Vercel project env, all environments (set via `edit_project_env`). Value never committed. |
| `EDGE_CONFIG_ID` + a Vercel write token | used only by the **local** publisher `scripts/push-data.py`; never set on Vercel, never committed |

Without `EDGE_CONFIG`, the route still returns 200 with the error envelope (the
`error: 'edge-config unavailable'` state), so a missing var degrades safely.

## Branch / commit for the deploy

- Branch: `feat/api-data-route` @ `67c6f49` — contains `api/data.js`,
  `package.json`, and `tests/api/`.
- **Do not use the remote branch `feat/junter-api-data`**: it is based on the old
  `main` and, if merged, reverts card 11's UI adapter (`ui/app.js`,
  `ui/tests/test_app.py`, `synthetic-data/*`). `feat/api-data-route` is rebased
  on current `main` (`6e62d00`) and preserves it.

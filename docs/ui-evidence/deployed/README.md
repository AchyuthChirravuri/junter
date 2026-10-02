# Junter UI — Deployed-State Evidence

Screenshots of the **live deployed site**, not the local prototype:

- URL: https://junter-xi.vercel.app
- Captured: 2026-10-02, against `main` @ `88577ae` (the live commit)
- Browser: real Chrome via CDP, viewport 1280×577, one PNG per screen
- Method: navigate each hash route, wait for `/api/data` to resolve, capture

## Data provenance (what "live data" means here)

Every screenshot is rendered from the same-origin `/api/data` endpoint, which
serves a **privacy-minimized projection of the real tracker** (144 roles,
68 distinct companies, 4 with a published deadline). `lastUpdated` on the
payload: `2026-10-02T13:05:40-04:00`. No emails, URLs, operator notes, or
immigration-specific blocked reasons are in the published projection.

## What to look at, in order

| # | File | Screen | Evidence of real data |
|---|---|---|---|
| 01 | `01-pipeline-board.png` | Pipeline Board | "144 roles · 5 columns · 144 loaded"; MASTERCARD, JPMORGAN CHASE, WIKIMEDIA FOUNDATION, GOOGLE, WELLFOUND |
| 02 | `02-deadline-rail.png` | Deadline Rail | "9 roles with a published deadline"; tier colours render — red (Cornell University, 1d), orange (0 in bucket), blue/accent (Comcast 19d, Spade 27d) |
| 03 | `03-focus.png` | Focus | Header + the self-report disclaimer banner; **no role rows render** (defect D-2, below) |
| 04 | `04-daily-digest.png` | Daily Digest | **Blank body** (defect D-1, below) |
| 05 | `05-role-detail.png` | Role Detail | **"Role not found: 1"** (defect D-2, below) |
| 06 | `06-run-health.png` | Run Health | **Blank body** (defect D-1, below) |
| 07 | `07-rubric-calibration.png` | Rubric & Calibration | **Blank body** (defect D-1, below) |
| 08 | `08-telegram-mirror.png` | Telegram Mirror | **Blank body** (defect D-1, below) |

## Defects found (flagged, NOT fixed in this card)

### D-1 — Engine screens throw on the live payload shape

Screens 4, 6, 7, 8 (and the "no interested roles" path of screen 3) render a
blank body because the live `/api/data` payload does not carry the arrays those
screens iterate. Root cause, confirmed by reading `ui/app.js` and the served
file:

- `app.js:362` sets `cron_runs: raw.run_health || []`
- `app.js:366` sets `telegram_messages: raw.telegram_messages || []`
- `app.js:361` sets `digests: digests`

The live payload has **only** `{roles, lastUpdated}` — no `cron_runs`,
`digests`, `rubric_versions`, or `telegram_messages`. The `|| []` fallbacks are
dead code on the live path.

The `normalizeState()` adapter (`app.js:~220`) deliberately returns the payload
unchanged when `Array.isArray(raw.roles)` is true (the live payload qualifies).
So `buildState` is never invoked for the live shape, and `state.cron_runs`
etc. are `undefined` → `Cannot read properties of undefined (reading 'filter'
/ 'forEach')`:

- `app.js:575` — `state.digests.forEach` (Daily Digest)
- `app.js:770` — `state.cron_runs.filter` (Run Health)
- `app.js:845` — `state.rubric_versions.forEach` (Rubric & Calibration)
- `app.js:901` — `state.telegram_messages.filter` (Telegram Mirror)

These are the four unhandled TypeErrors in the console. This matches the
honest deviation Card 7 already flagged: the deployed route publishes a
minimized `{roles, lastUpdated}` projection, whereas the engine screens expect
the full exporter contract (`run_health`, `digests`, `rubric_versions`,
`telegram_messages`).

### D-2 — Role Detail id type mismatch

Clicking any Pipeline Board card (e.g. MASTERCARD → `#/role/9`) shows
**"Role not found: 9"**, even though role 9 exists in the live payload.

Root cause: `renderRole` (`app.js:614`) matches
`state.roles.filter(r => r.id === roleId)`. The live payload emits numeric ids
(`{"id": 9, ...}`), but the hash route supplies a **string** (`parts[1]`), so
`9 === "9"` is false for every role. The same string/number mismatch is why
`#/role/1` returns "Role not found: 1". The Focus screen (which filters to
`status === 'interested'`) is empty on the live payload because its statuses
are lowercase (`packaged`, `pinged`, …) while the route/template expects the
engine's `interested` bucket.

## What IS verified working

- Deployed site loads: `/` → HTTP 200, `/api/data` → HTTP 200 valid JSON.
- Pipeline Board: 144 roles across 5 columns, real companies.
- Deadline Rail: real deadlines with correct red/orange/blue tier colours and
  day-counts (1d / 19d / 27d …).
- No 500 responses on any resource; no unhandled promise rejections.

## Console findings

- Zero HTTP 5xx responses across the session.
- Four `Uncaught TypeError` errors, all from defect D-1 (`app.js:575`, `770`,
  `845`, `901`). No `unhandledrejection` events.

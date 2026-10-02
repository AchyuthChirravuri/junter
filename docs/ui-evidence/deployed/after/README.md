# Junter UI — Deployed-State Evidence (after the live-payload fix)

Screenshots of the **live deployed site** after the D-1/D-2 fix landed
(commit `752416d`, deployed as `dpl_HDRmqzUvDCrnPjaEexKVFEPHyp1C`):

- URL: https://junter-xi.vercel.app
- Captured: 2026-10-02, against `main` @ `752416d` (the live commit)
- Browser: real Chrome via CDP, viewport 1280×577, one PNG per screen
- Method: navigate each hash route, wait for `/api/data` to resolve, capture

The `../*.png` (one level up) are the **before** set captured by the
verification card against `main` @ `88577ae`, where four screens were
blank / "Role not found". This `after/` directory is the **same eight
screens** re-captured once the fix deployed. Keep both: the pair is the
evidence that the defects were real and are now closed.

## Data provenance

Every screenshot renders from the same-origin `/api/data` endpoint, which
serves a **privacy-minimized projection of the real tracker** (144 roles,
68 distinct companies, 9 with a published deadline). `lastUpdated`:
`2026-10-02T13:05:40-04:00`. No emails, URLs, operator notes, or
immigration-specific blocked reasons are in the published projection — the
minimization is unchanged by this fix (option (b): teach the UI to tolerate
the minimized payload, publish nothing new).

## What changed, screen by screen

| # | File | Screen | Before (Card 9) | After (this fix) |
|---|---|---|---|---|
| 01 | `01-pipeline-board.png` | Pipeline Board | 144 roles, 5 columns (worked) | unchanged — 144 roles, 5 columns |
| 02 | `02-deadline-rail.png` | Deadline Rail | 9 deadlines, tier colours (worked) | unchanged — 1 / 0 / 8 by tier |
| 03 | `03-focus.png` | Focus | header only, **no rows** | 15 real `routed=int` roles render |
| 04 | `04-daily-digest.png` | Daily Digest | **blank body** (D-1) | honest "No digest data published" empty state |
| 05 | `05-role-detail.png` | Role Detail | **"Role not found: 1"** (D-2) | MASTERCARD role 9 resolves, real fields |
| 06 | `06-run-health.png` | Run Health | **blank body** (D-1) | summary cards show "—", honest empty state |
| 07 | `07-rubric-calibration.png` | Rubric & Calibration | **blank body** (D-1) | honest "No rubric data published" empty state |
| 08 | `08-telegram-mirror.png` | Telegram Mirror | **blank body** (D-1) | honest "No Telegram traffic published" empty state |

Unlike the before set, all eight `after/` PNGs are **byte-distinct** — no
two screens share a hash any more, because no renderer throws before it
paints.

## What the fix did

Two defects, both rooted in the UI assuming the full exporter contract
while the deployed `/api/data` publishes only `{roles, lastUpdated}`:

- **D-1** — `normalizeState()` returned the payload unchanged whenever
  `Array.isArray(raw.roles)` held (the live shape qualifies), so
  `state.digests`, `cron_runs`, `rubric_versions` and `telegram_messages`
  were `undefined` and four renderers threw on `.forEach` / `.filter`.
  It now defaults any unpublished screen section to `[]` (in place, same
  reference — still idempotent) and flags the state `minimized`, so those
  four screens show an explicit "not published" card instead of a blank
  body. Run Health's summary is derived from the published run list rather
  than the hard-coded "7 / 7" / "12 / 30", and Role Detail no longer
  invents artifact filenames, a multi-step history, or illustrative rubric
  bars on the live path.
- **D-2** — `renderRole` compared `r.id === roleId`; the payload emits
  numeric ids while the hash route supplies a string (`9 === "9"` false),
  so no role ever resolved. Both sides are now compared as strings. Focus
  matched `status === 'interested'`, a value the engine never publishes
  (interest lives in the `routed` column), so it now matches
  `routed === 'int'`.

Regression tests pin both fixes against the real `ui/app.js`
(`ui/tests/test_app.py`: `MinimizedPayloadTests`, `RoleIdMatchTests`); the
offline FALLBACK path is unchanged.

## Verification (live, real browser, post-deploy)

- All 8 hash routes render non-blank bodies — 8/8, confirmed above.
- Clicking the first Pipeline card (MASTERCARD) opens `#/role/9` and shows
  that role's detail; no "Role not found".
- Browser console: **zero unhandled errors/rejections on every route**
  (was 4 uncaught TypeErrors at `app.js:575/770/845/901`).
- Deadline Rail + Pipeline Board still show the same real data (no
  regression): 144 roles / 5 columns; rail 1 this-week, 0 next-week,
  8 this-month+.
- Deployed `app.js` (md5 `35fdc10e9cc02ddfc7986a32cef59e4a`) is byte-identical
  to committed `main`.

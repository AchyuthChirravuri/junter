# Junter UI — Visual Evidence

Before/after screenshots documenting the Figma polish (T5) and the
HTML prototype sync (T6) work from 2026-10-01. Every PNG in this
directory is the actual screenshot a worker captured against the
live Figma file (`e4kzWfgPUTchpIcuv1o7Y6`) or the local HTML
prototype at `../../ui/index.html`.

## What to look at, in order

**1. Figma before** — `figma-before/` — the pre-polish state of the
live Figma file. 8 PNGs covering the affected screens (D-1, D-2, D-3)
plus the other 5 screens that were re-reviewed for regressions.

| File | What |
|---|---|
| `D1-rolename-rename.png` | Role Detail (Screen 5) — Drafts card filenames broken vertically into single-char lines (the D-1 bug) |
| `D2-focus-robinhood.png` | Focus (Screen 2) — Robinhood card padding drift on all four Focus cards |
| `D3-digest-link.png` | Daily Digest (Screen 4) — "View full digest →" link hugging the right edge |
| `full-1-pipeline.png` | Pipeline Board (Screen 1) — unaffected by the polish; reference for what "untouched" looks like |
| `full-3-deadline.png` | Deadline Rail (Screen 3) — hero reference |
| `full-6-runhealth.png` | Run Health (Screen 6) — also verified for regressions |
| `full-7-rubric.png` | Rubric & Calibration (Screen 7) — also verified for regressions |
| `full-8-telegram.png` | Telegram Mirror (Screen 8) — also verified for regressions |

**2. Figma after T5** — `figma-after-T5/` — the live Figma file
post-polish. 3 PNGs covering the three fixes that landed.

| File | What |
|---|---|
| `Role-Detail-D1.png` | D-1 fixed: filenames render as a single truncated line in monospace, no vertical break |
| `Focus-D2.png` | D-2 fixed: all 4 Focus cards have uniform `space/5` (16px) padding on all four sides; Robinhood aligned with the others |
| `Daily-Digest-D3.png` | D-3 fixed: "View full digest →" link sits `space/6` (24px) from the card's inner right edge instead of the outer frame edge |

**3. HTML after T6** — `html-after-T6/` — the local HTML prototype at
`../../ui/index.html` synced to the post-T5 Figma state. 4 PNGs.

| File | What |
|---|---|
| `Role-Detail-D1.png` | D-1 synced: filename span has ellipsis truncation + `ui-monospace` font family |
| `Focus-D2.png` | D-2 synced: gate-box padding uses the design token |
| `Daily-Digest-D3.png` | D-3 synced: "View full digest →" link anchored with `margin-right: var(--space-6)` |
| `Sidebar-D4.png` | D-4 synced: SPA equivalent of the Figma Title-page pointer — a sidebar hint reads "→ see all 8 screens in the wireframe file" (D-4 was N/A in Figma because the live file has 1 page and 8 Screen frames side-by-side, not 9 separate pages) |

## Companion notes

- [[../ui-stage-0|Junter UI — Stage 0 problem definition]] — the original brief that named deadline-first sorting as the differentiator
- `../../README.md` — top-level project landing; mentions this evidence directory

## Source provenance

- All Figma screenshots: `mcp__figma__get_screenshot` against file
  `e4kzWfgPUTchpIcuv1o7Y6`, captured by T5 (Figma polish worker) on
  2026-10-01 between 02:18 and 02:28 ET.
- All HTML screenshots: headless browser capture against
  `ui/index.html`, captured by T6 (HTML sync worker) on 2026-10-01
  after the patches landed.
- Source transcripts and PROGRESS logs:
  - T5: `~/Hermes-workspace/temp/junter-class/T5/junter-overnight/PROGRESS-T5.md`
  - T6: `~/Hermes-workspace/temp/junter-class/T6/junter-overnight/PROGRESS-T6.md`
  - Live kanban board: `junter-class-2026-10-01` (T5 = `t_412ca47b`, T6 = `t_2a4b8877`)

## D-4 note

D-4 (Title page pointer) was N/A on the live Figma file because the
file has 1 page with 8 Screen frames side-by-side, not 9 separate
pages. The HTML equivalent was added as a sidebar hint — see
`html-after-T6/Sidebar-D4.png`. This is documented honestly in the
Figma polish report (T5) and the HTML sync report (T6).
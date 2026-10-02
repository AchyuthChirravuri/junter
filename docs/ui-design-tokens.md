# Junter — Design Tokens (v1)

Single source of truth for the wireframe set. Apply to every screen so the
seven pages read as one product. Keep this file short — three ramps, four
corner radii, six spacings. Add a token when you've used the same value three
times across the file.

All values are in CSS-style units that map 1:1 to Figma in the layout that
follows (auto-layout, `itemSpacing`, `padding*`).

## Typography

Single family: **Inter** (preloaded, free, supports the full Latin set we need).

| Token | Size / line-height / weight | Used for |
|---|---|---|
| `text/display` | 32 / 40 / Semi Bold | Hero numbers on the deadline rail ("8 days"), page titles on role detail |
| `text/display-large` | 40 / 48 / Semi Bold | Secondary hero numbers on the deadline rail (e.g. "Today" counts); the wireframes use `fontSize = 20` for inner-card counters, `fontSize = 40` for the largest rail tile |
| `text/h1` | 24 / 32 / Semi Bold | Section titles, card titles on the pipeline board |
| `text/h2` | 18 / 26 / Semi Bold | Subheadings, role titles inside cards |
| `text/body` | 14 / 22 / Regular | Body copy, backgrounder text, role descriptions |
| `text/meta` | 12 / 18 / Regular | Timestamps, source labels, count badges |
| `text/meta-tight` | 11 / 16 / Regular | Densely-packed meta rows (digest timestamps with side-by-side actions, telegram preview timestamps); the wireframes use this for cases where `text/meta` (12px) feels too loose |
| `text/mono` | 13 / 20 / Regular, Inter (Mono fallback acceptable) | Tracker IDs, app URLs, command references |

No italics, no display faces. Information density matters more than character.

## Spacing scale (px)

Use these exact values. Six steps. If you need a seventh, add it here first.

| Token | Value | Typical use |
|---|---|---|
| `space/2` | 4 | Tight icon-to-label gap |
| `space/3` | 8 | Inside-tag padding (vertical) |
| `space/4` | 12 | Default inner padding of small components (chips, meta rows) |
| `space/5` | 16 | Default inner padding of medium components (cards, rows) |
| `space/6` | 24 | Gap between related sections inside a card |
| `space/7` | 32 | Outer card padding, page gutters |

Page-level horizontal gutter is `space/7` (32px). Page max width is 1200px.

## Color (light theme v1)

Eight colors total. Anything beyond these eight is "add it to this file first."

| Token | Hex | Used for |
|---|---|---|
| `color/bg` | `#FFFFFF` | Page background |
| `color/surface` | `#F7F8FA` | Card backgrounds, subtle raised areas, secondary surfaces |
| `color/border` | `#E5E7EB` | 1px dividers, card outlines, table rows |
| `color/text-primary` | `#111827` | Body and heading text |
| `color/text-secondary` | `#6B7280` | Meta, timestamps, secondary labels |
| `color/accent` | `#2563EB` | Primary action buttons, links, selected nav item |
| `color/warning` | `#D97706` | Deadline alerts ("8 days left"), status = pinged with deadline |
| `color/danger` | `#DC2626` | Errors, blocked rows, "stale" warnings |
| `color/success` | `#10B981` | Submitted status, "ready" affordances, positive confirmations |

Semantic status colors are applied via these tokens. Do not introduce new reds,
greens, yellows, blues. Status text uses `text/secondary` for the label and the
semantic color for the dot/badge.

## Corners

| Token | Value | Used for |
|---|---|---|
| `radius/sm` | 4 | Inline tags, chips |
| `radius/md` | 8 | Buttons, inputs, small cards |
| `radius/lg` | 12 | Role cards, large panels |

## Elevation

Avoid shadows. Use `color/surface` to distinguish raised content from the page
background. The only shadow we allow is `0 1px 2px rgba(17,24,39,0.06)` on
overlays (modals, dropdowns). Defined here so the rule is explicit:

```
shadow/overlay: 0 1px 2px rgba(17,24,39,0.06)
```

## What is NOT in v1

- No light/dark theme switching — light only for v1, dark in a later phase.
- No component library yet. We use raw auto-layout frames and document a
  reusable pattern in `docs/components.md` once we've drawn the same shape
  three times.
- No icons beyond simple geometric shapes (dot, square, triangle for status).
  Icon work comes after the wireframes are approved.

## Token drift resolution (2026-10-01)

The first token-consistency check against the live Figma file
(`junter-overnight/PROGRESS-T5.md`, 2026-10-01) found **134 node-property
values** that did not match a token. Two large classes:

1. `fontSize = 11` on dozens of meta-text nodes (token spec defined `text/meta = 12`).
2. `fontSize = 20` and `fontSize = 40` on the deadline-rail hero numbers (token spec defined only `text/display = 32`).

**Resolution:** added `text/meta-tight` (11/16 Regular) and
`text/display-large` (40/48 Semi Bold) above. The values were not
errors — they were a refinement of the v1 token spec, used
intentionally by the wireframes for tighter meta rows and bigger
hero counts. The 134 drift values now have a token home and the
HTML/CSS can adopt them without inventing new literals. The
`text/display` (32) and `text/meta` (12) tokens remain the **default**
for these use cases; the new tokens are explicit second-pass
refinements.

This is the canonical resolution pattern: when a token spec is
outgrown by real usage, **add tokens, do not sweep values back**.

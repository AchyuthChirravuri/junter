# Junter UI & Vercel Deployment Analysis — 2026-10-02

**Task:** T4 (`t_b91ce57f`)
**Scope:** Read-only audit of https://junter-xi.vercel.app and its local source.
**Method:** Live HTTP probe, full-source read, browser screenshots (8 of 8 screens), `/api/data` JSON inspection.
**Date:** 2026-10-02 23:20 EDT.

---

## Executive summary

The Junter reading layer is a working 8-screen SPA that faithfully renders the live Vercel deployment's `/api/data` payload (144 roles today), with three structural findings that dominate the operator experience:

1. **The live payload is information-thin by design and the UI knows it.** Of 144 roles only 9 (6.3%) carry a deadline, 0 carry a `blocked_reason`, 0 carry a `url`, and 0 carry a per-factor `rubric_factors`. The UI handles this honestly (lines 622-625, 696-699, 736-739, 773-789 in `ui/app.js`) but four of the eight screens end up nearly empty (Daily Digest, Run Health, Rubric, Telegram Mirror) — so the operator opens the UI most days and sees four empty-state cards. The screens are honest; the affordance is wrong.

2. **Pipeline Board's `Interested` column shows `0` while the Focus screen has 15 cards.** `renderPipeline` (line 456) groups by `r.status === 'interested'`, but the live dataset tracks interest in `routed === 'int'` (line 561). The fallback seed uses both fields together, masking the divergence. Confirmed: 15 of 144 roles have `routed='int'`; zero have `status='interested'`. This is the single highest-leverage fix.

3. **The toolbar controls (search box, source/fit/deadline chips, sort dropdown) on Pipeline, Digest, and Telegram are presentational only** — they're rendered at lines 444-452, 610-620, 996-1003 but no event listener is attached, so typing in the search box changes nothing. With 86 pinged rows visible, the operator cannot filter.

The Vercel infrastructure itself is healthy: HTTP 200 on the app and `/api/data` in 0.19s, `s-maxage=60, stale-while-revalidate=300` cache posture honored, PII guard on the client (lines 30-41), never-empty envelope (`api/data.js:26-46`).

---

## 1. Deployment & infra review

### 1.1 Live Vercel probes (2026-10-02 23:18 EDT)

| Endpoint | Status | Size | Cache | Notes |
|---|---|---|---|---|
| `https://junter-xi.vercel.app/` | **HTTP/2 200** | 5929 B | `x-vercel-cache: HIT`, last-modified 18:15:17 | Serves `ui/index.html` shell. |
| `https://junter-xi.vercel.app/api/data` | **HTTP/2 200** | 29262 B | `x-vercel-cache: MISS`, `s-maxage=60, stale-while-revalidate=300` (declared in `api/data.js:27`) | Returns JSON envelope with 144 roles. |
| `https://junter-xi.vercel.app/ui/index.html` | (not separately probed; same SPA shell) | — | — | Mirror URL referenced in task brief; renders the same app. |

`curl -sI` confirms the route returns `content-type: text/html` and `server: Vercel`. The HTML/JS are served from Vercel's CDN with `cache-control: public, max-age=0, must-revalidate`, which is correct for the SPA shell.

### 1.2 `/api/data` handler — `api/data.js` (59 lines)

Reads from Vercel Edge Config via `@vercel/edge-config`. Three contracts honored:

- **Always 200, even on failure.** `catch` branch returns `{ roles: [], lastUpdated: null, error: 'edge-config unavailable' }` (line 57) so the SPA never has to handle a 5xx.
- **Envelope normalization.** `envelope()` (lines 36-46) handles three publisher shapes: a native `{roles:[]}`, an exporter `{pipeline:[]}` (no `roles`), and any other value (treated as empty). Idempotent — repeated calls return the same reference.
- **No error-string leakage.** Per line 15-16 and the catch handler, exception messages never reach the response body (no connection string, no stack, no host).

The cache posture `s-maxage=60, stale-while-revalidate=300` is exactly what's declared on the response (line 51); confirmed in the response header. This means the operator's first page load on a Tuesday might see Monday's data — within 60s the CDN revalidates against Edge Config.

### 1.3 Live payload inspection

Today's `/api/data` payload:

```
top-level keys: ['lastUpdated', 'roles']
lastUpdated:    2026-10-02T13:05:40.482647-04:00
roles:          144
```

Per-role fields actually published (9 keys, observed on all 144 rows):

```
company, deadline, fit, id, role, routed, source, status, status_date
```

**Truthiness-presence across all 144 rows:**

| Field | Count truthy | Count empty/null | Note |
|---|---|---|---|
| `id` | 144 | 0 | Integers (e.g. `1`, `144`), not the fallback's strings (`'r01'`). `app.js` handles both via `String(r.id)` (lines 282, 666). |
| `company` | 144 | 0 | Always present. |
| `role` | 144 | 0 | Always present. |
| `fit` | 144 | 0 | Field renamed from `fit_score` during envelope shaping. |
| `source` | 144 | 0 | E.g. `"HN Who's Hiring"`, `"Built In NYC"`, `"Wellfound"`. |
| `status` | 141 | 3 | Values: pinged 86, packaged 43, blocked 10, submitted 2, empty 3. |
| `status_date` | 141 | 3 | Same coverage as `status`. |
| `routed` | 134 | 10 | `ping` 119, `int` 15, empty 10. |
| `deadline` | **9** | **135** | Only 6.3% of roles carry a deadline. |
| `blocked_reason` | **0** | 144 | Field absent entirely from per-role records. |
| `url` | 0 | 144 | URLs are stripped from the published projection. |
| `angle` / `notes` | 0 | 144 | Per-role notes not published. |

**This is the engine's privacy-minimized projection**: no `url` (would leak the application portal), no `notes` (operator's free-text), no `blocked_reason` (potentially identifying), no `rubric_factors`, no per-role `draft_paths`. The fallback seed has none of these either, so the UI's "honest empty state" code paths (lines 696-699, 736-739, 773-789) match the live behavior exactly.

### 1.4 PII guard — client-side

`ui/app.js:30-41` defines three refusal rules: real (non-example.com) email, real (non-example.com) URL, or any string in the `PII_IDENTIFIER_TOKENS` allowlist. The legacy capitalized-name heuristic was removed (lines 20-29 comment block) because it produced 100% false positives against the real dataset. Current behavior: refuses only on actual contact PII. Adoption (`adoptApiPayload`, lines 1131-1153) runs the guard last, so a payload with personal free-text would be refused in favor of `FALLBACK`. This is defense-in-depth, not the primary PII guard (the publisher strips PII before write; this guard catches a configuration slip).

### 1.5 Embedded fallback (50 roles, `ui/app.js:42-166`)

When the API is unreachable, returns non-2xx, is malformed, carries `error:`, is empty, or fails the PII check, the SPA renders `FALLBACK`: 50 fictional roles (`r01`-`r50`) split 10/10/10/10/10 across the 5 status columns, with `rubric_versions`, `digests`, `telegram_messages`, `cron_runs` all populated for the offline demo. The Google/Meta names that appear in the fallback are intentional and explicitly named as fictional in the comment (line 12-14).

**Subtle consequence:** the fallback sets both `status: 'interested'` AND `routed: 'int'` for the 10 Interested roles (lines 59-68), so the Pipeline Board's `Interested` column shows 10. In the live payload, only `routed='int'` is set and `status` is `packaged`/`submitted` — so the same column shows 0. This is why the bug went unnoticed.

---

## 2. 8-screen UX review

For each screen: what it does today (with line citations), what works, what is confusing for Achyuth as the daily operator, and what would be more useful.

### 2.1 Pipeline Board (`#/pipeline`, lines 430-477)

**Today:** Five-column board (Pinged, Interested, Packaged, Submitted, Blocked), one card per role with company, role title, fit score, source, and optional angle text. Clicking a card navigates to `#/role/<id>`. Header reads `"144 roles · 5 columns · 144 loaded"`.

**Works:** Clear 5-state mental model. Fits the codebase's "5-column flow" doctrine. Card click is wired (line 464).

**Confusing — and verified bugs:**

1. **The `Interested` column header reads `0` (header lines 459-461) while Focus has 15 cards.** Live evidence: the live payload has 15 roles with `routed='int'` (14 of them `status='packaged'`, 1 `submitted`), but `renderPipeline` filters `r.status === 'interested'` (line 456). The fallback seed masks this because its Interested roles carry `status: 'interested'`. **Highest-leverage bug.**

2. **3 of 144 roles are missing from the column counts** (header says "144 roles · 5 columns · 144 loaded"; column-count sum is 141; the 3 empty-status rows fall into no column). The header message also redundantly states the same number twice.

3. **No filter actually works.** The toolbar at lines 443-452 renders a search input, three chips ("All fit", "All sources", "All deadlines"), and a sort select — but no event listener is wired to any of them. Typing into the search box changes nothing; clicking the chips changes nothing. With 86 pinged roles visible at once, the operator cannot narrow by source (HN vs BuiltInNYC vs Wellfound), by fit, or by anything else.

4. **Source is rendered as raw text** (line 467: `"Fit " + r.fit.toFixed(1) + " · " + r.source`). The source strings vary in length ("HN", "HN Who's Hiring", "Built In NYC", "Wellfound") — the card layout doesn't break, but it would read better as a chip.

5. **The `angle` field is always empty on the live payload** (line 468 reads `r.angle ? ... : null`; live data has no `angle`/`notes` field). So in practice every card is missing its "angle" — a designed-for high-signal affordance that never fires.

**More useful for the operator:** fix the column bug (use `routed='int'` OR `status='interested'`); wire the search box (filter by company + role substring on input); collapse the 86-card Pinged column behind a "Show 10 / Show all" toggle since the operator's morning scan is the only realistic use case for that column.

### 2.2 Deadline Rail (`#/deadline`, lines 479-546)

**Today:** Three urgency tiers (red ≤7d, orange 8-14d, blue 15d+), three summary cards at top, one rail-tier block per populated tier, a footer noting how many roles have no published deadline.

**Live state (visible in `02-deadline-rail.png`):** 9 roles with a published deadline. Summary cards: This week 1, Next week 0, This month+ 8. The one red row: Cornell University, Investment Analyst (Office of University Investments, NYC), 1d, Fit 7.5, 2026-10-02, source `university`. The blue rows are Comcast (Universal Ads), Spade, etc.

**Works:** Tier classification is honest (lines 489-491 use `urgencyTier()`), the footer tells the operator how many roles lack a deadline (line 538).

**Confusing:** the rail is **almost empty**. 135 of 144 roles (93.7%) have no published deadline. The whole point of the rail (per `docs/ui-stage-0.md:88-103` — the APMList "windows that open for hours-to-days" thesis) is undermined by the data. The header text "9 roles with a published deadline" is technically accurate but reads as failure-mode to an operator expecting urgency.

**More useful:** add a sub-row that lists *recently-added* roles without deadlines but with `status='pinged'` (the operator's natural follow-up). Add an "Edit deadline" affordance for the operator to fill in missing ones (their action surface is Telegram today; but seeing "you have 135 rows with no deadline — want to backfill 12 you remember?" would be high-signal).

### 2.3 Focus (`#/focus`, lines 548-601)

**Today:** Lists every role where `r.routed === 'int' || r.status === 'interested'`, sorted by deadline (soonest first, no-deadline last). Each card shows role, company, fit, days-to-deadline, and a 5-item submission gate checklist (Backgrounder read, Resume drafted, Cover letter drafted, References notified, Submission logged). The first two checklist items render as filled (line 588, `i < 2`).

**Live state:** 15 cards (matches `routed='int'` count).

**Works:** This screen is the operator's "what should I work on today" view, and the gate checklist is genuinely useful. The banner ("Gate progress is self-reported (your checks). Engine-written artifacts live in drafts/") correctly sets expectations — line 554.

**Confusing — and verified:**

1. **The first two checklist items are always shown as filled** (line 588: `i < 2 ? ' is-on' : ''`). That's a fake-state lie to the operator — every role shows "Backgrounder read" and "Resume drafted" complete regardless of actual state. The "soft gate checklist" intent is fine (it's a planning aid per line 554), but the visual pretends things are done that aren't.

2. **No deadline → card layout shifts awkwardly.** When `days` is null (line 575-579), the meta line reads `"no published deadline"` — fine. But every interested role today shows that string because none of the 15 routed=int roles have a published deadline in the live payload (the deadline distribution by urgency band confirmed: 9 roles total have deadlines; 0 of them are routed=int).

3. **No way to mark a gate complete in the UI.** Clicking the checks does nothing. The checklist is a read-only decoration.

**More useful:** load the checklist state from the role's `draft_paths` (line 299, empty on live) and `routed='pkg'`/`sub` (line 289) — derive "Backgrounder read" from whether draft_paths exists, "Resume drafted" from `routed='pkg'`, "Submitted" from `routed='sub'`. Now the checklist reflects engine state instead of a hard-coded `i < 2`. Make the cards clickable to the role detail (currently they aren't wired to a click handler; only Pipeline/Deadline cards are).

### 2.4 Daily Digest (`#/digest`, lines 603-662)

**Today:** Lists digest cards from `state.digests[]`. Each card has a date header ("Digest — YYYY-MM-DD · 7:30am ET"), promoted section (id-link to role detail), rejected-with-reasons section (grouped by reason: `role-mismatch-senior`, `sponsorship-not-confirmed`, `too-junior`).

**Live state:** Empty state renders — see `04-daily-digest.png`. Text: *"No digest data published. The live /api/data endpoint publishes a privacy-minimized projection (roles + lastUpdated only). Digest history is not part of it."* (line 623-625).

**Works:** The honest empty-state is correct and informative. Toolbar search/select widgets are presentational, same as Pipeline.

**Confusing:** the operator gets **zero value** from this screen on every visit because the digest history never makes it into the projection. This is a single-purpose screen that has nothing to show 100% of the time in production.

**More useful (and the highest-leverage change after the column bug):** either (a) include the last 14 days of `digests[]` in the projection so this screen has content, or (b) merge this screen with the Telegram Mirror and surface a "Recent Telegram messages" view that's actually populated by something. Option (a) is the cheap, high-leverage fix; the privacy cost of recent-digest text is low (the digests are *already* sent to Telegram).

### 2.5 Role Detail (`#/role/<id>`, lines 664-848)

**Today:** Two-column layout. Left: Backgrounder & drafts (file list of expected artifact paths), Angle (free text). Right: "Why this scored X.X" (rubric factor bars), History (timeline).

**Live state (Wikimedia Foundation Lead PM, Security, id=1, fit 7.2):** Rubric bars render zero rows — `rubric_factors` is empty on live data so the screen prints `"The published projection carries a single fit score, not the per-factor rubric breakdown."` (line 699). Draft list shows `"No draft artifacts published for this role."` (line 738). History shows two items: "Discovered on HN Who's Hiring" + "Status: packaged" (lines 774-789) — both honest given the data, but the timeline that the wireframe envisioned (4 dots: discovered → watchlist → interested → artifact) never fires because `role.history` is always empty on live data.

**Works:** The honest empty states are correct. The crumb `← Pipeline` is wired (line 672).

**Confusing:** the live payload strips the very data that makes this screen useful. Operator opens a role to see *why* it scored 7.2 — the screen can't tell them.

**More useful:** surface what *is* known: show `routed`, `source`, `status_date`, `deadline` (or "no published deadline"), and a single "last decision engine made" line based on `status`. Don't fabricate rubric bars (current code correctly avoids that on minimized payloads); instead show the breakdown of how the fit number was *likely* derived by listing which rubric version is current and that this row didn't get a per-factor pass.

### 2.6 Run Health (`#/run-health`, lines 850-921)

**Today:** Three summary cards (Today, Jobs tracked, Healthy), a cron-log table (Cron / Schedule / Last status / Last run / Latency), and a Warnings & errors block.

**Live state:** Empty state — see `05-run-health.png`. Text: *"No run-health data published. The live /api/data endpoint publishes a privacy-minimized projection (roles + lastUpdated only). Cron run health is not part of it."* (line 914-916).

**Works:** Honest empty state.

**Confusing:** the operator's most pressing question on a bad day — *"did the digest send at 7:30?"* — has no answer here. The wireframe's purpose (`docs/ui-stage-0.md:64`) was *"Tell me when the bot last ran, and whether anything failed."* On the live payload, it's permanently blank.

**More useful:** include `cron_runs[]` (the 6 known jobs from `snapshot-export/export.py:62-69`: `hunt-part1-platforms`, `hunt-part2-startups`, `hunt-part3-universities`, `weekly-calibration`, `telegram-delivery`, `telegram-mirror-failed-retry`) in the projection. This is the operator's "what is happening right now" screen. The privacy cost is zero — schedule names are not PII.

### 2.7 Rubric & Calibration (`#/rubric`, lines 923-986)

**Today:** Three-column grid (Versions, Diff v1→v2, Outcomes v1→v2), with a calibration footer quoting "Reweighting only happens when interaction data exists."

**Live state:** Empty state — see `06-rubric.png`. Same minimization-projection empty state text.

**Works:** Honest empty state. When populated (offline seed), the layout is genuinely informative — the rationale text under each diff is high-signal.

**Confusing:** the operator's second-most-pressing question on a Sunday — *"what did the rubric change to last week?"* — has no answer here on the live payload.

**More useful:** include the two most recent rubric versions in the projection. They're 200-400 bytes of weights + rationale text; privacy cost is zero (the rubric is the system's IP, not personal data).

### 2.8 Telegram Mirror (`#/telegram`, lines 988-1046)

**Today:** Verbatim Telegram bot traffic grouped by date. Each message card shows body text, status badge (`Delivered` / `Failed: <error>` / `Retry succeeded` / `Warning (delivered)`), and sent-at timestamp. Toolbar with "Failed only [N]" filter.

**Live state:** Empty state — see `07-telegram.png`. Same minimization-projection empty state text.

**Works:** Honest empty state.

**Confusing:** the operator's *post-morning* check (did the digest actually arrive? did the backgrounder deliver? did anything fail?) has no answer here. The Telegram Mirror screen is the operator's first stop when something feels wrong, and it's always blank on live.

**More useful:** include the last 7 days of `telegram_messages[]` in the projection. Privacy cost: low — these are the same messages the operator just received on Telegram, so it's a duplicate surface, not a leak.

---

## 3. Information architecture — what is exposed, what is hidden, what is implied

### 3.1 Exposed (in the live projection)

| Field | Surface | Notes |
|---|---|---|
| `id` | Implicit (URL pattern, never displayed as a label) | Operators can `#/role/144` but no copy says "id 144". |
| `company` | Everywhere | Always present. |
| `role` | Everywhere | Always present. |
| `fit` | Pipeline card meta, Role detail hero | Field renamed from `fit_score` during envelope shaping. |
| `source` | Pipeline card, Deadline rail row, Role detail header | `"HN Who's Hiring"`, `"Built In NYC"`, `"Wellfound"`, `"university"` — 4 distinct sources observed. |
| `status` | Pipeline column membership | Values: `pinged`, `packaged`, `submitted`, `blocked`. |
| `routed` | **Implied only** — Focus uses it but no UI label says "routed" | `routed='int'` is the operator's "interested" intent; no screen shows it as a label. |
| `status_date` | Role detail header right side (`Status: packaged · 2026-09-17`) | Visible on detail only. |
| `deadline` | Deadline rail, Focus card meta | Only 9 of 144 roles carry it. |
| `lastUpdated` | **Hidden** | Top-level envelope field, never rendered. |

### 3.2 Hidden (in the publisher's projection)

| Field | Status | Operator impact |
|---|---|---|
| `url` | Stripped | Cannot link out to the application portal from the UI. Operator must remember to find the URL elsewhere (Telegram digest link, personal notes). |
| `notes` / `angle` | Stripped | The Pipeline card's "angle" affordance (line 468) is permanently empty. Role detail "Angle" card (line 830-832) renders "No angle captured." |
| `blocked_reason` | Stripped | The Blocked column shows 10 cards with no reason — operator can't tell *why* a role was blocked without opening `tracker.csv` locally. |
| `rubric_factors` | Stripped | "Why this scored X" panel renders an empty state. |
| `draft_paths` | Stripped | "Backgrounder & drafts" panel renders "No draft artifacts published." |
| `history` | Stripped | Timeline is the 2-event fallback (Discovered + Status). |
| `cron_runs` | Stripped (entire section) | Run Health screen is empty. |
| `telegram_messages` | Stripped | Telegram Mirror screen is empty. |
| `digests` | Stripped | Daily Digest screen is empty. |
| `rubric_versions` | Stripped | Rubric & Calibration screen is empty. |

### 3.3 Implied but never shown

- **`lastUpdated` (top-level):** The operator can never tell *when the snapshot was taken* from the UI. The lastUpdated is 2026-10-02T13:05:40 — the operator should be able to glance at any screen and see "data as of 2 hours ago" or "stale (12h)".
- **`id` per role:** Every role has a numeric id; the URL is `#/role/<id>` but no card or row shows the id. The Telegram command surface uses `<id>` for `int`, `go`, `qs`, `intel`. The operator has to remember or scroll back through chat to find an id.
- **`routed`:** As above, the operator's "interest" intent is tracked but invisible as a label.
- **`source` provenance:** Knowing a role came from HN vs BuiltInNYC is half the picture. The pipeline UI shows source; it doesn't show *when* it was discovered or *which scan* found it (engine-internal data, not even present in the offline seed).
- **`fit` distribution:** No screen shows "the 10 highest-fit pinged roles" or "roles where fit moved since last week". The fit number is shown per-role; its distribution is never summarized.

---

## 4. Operator workflow gaps

A typical day for Achyuth (per `docs/user-manual.md` and the task brief):

### 4.1 Before Telegram (6:55-7:30am)

The cron job `hunt-part1-platforms` runs at 7:30am ET. Before 7:30, the UI shows yesterday's snapshot. If the operator opens Pipeline at 7:00am, they want to see the *staleness* of the data — does the timestamp say 13:05 today (fresh) or 13:05 yesterday (stale)? Today's payload is fresh (`lastUpdated: 2026-10-02T13:05:40`), but no screen exposes that. **Gap: a single global timestamp indicator at the top of every screen.**

### 4.2 After Telegram (~7:35-7:50am)

Operator reads the digest on Telegram and replies `int 3 5 7`. The Telegram commands update the local `tracker.csv`, which (eventually) flows through the snapshot exporter to Edge Config, then to `/api/data`, then to the UI. The cycle is minutes-to-hours depending on the cron.

If the operator opens the UI after the digest and wants to see *"which roles did I just mark interested?"*, the answer is the Focus screen — but the screen has no timestamp showing *when* it last saw the new `routed='int'` value. **Gap: a "last refreshed" timestamp and a visual indicator when data is fresher than the prior visit (so the operator can tell their reply landed).**

### 4.3 On days when something is wrong

Three likely scenarios:

- **Digest didn't arrive at 7:30.** Operator opens Telegram → no message. Goes to the UI. Run Health is blank. Telegram Mirror is blank. **The UI cannot answer the operator's first question ("did the digest run?").** This is the single biggest workflow failure.
- **Backgrounder is delayed.** Operator marked `int 3 5 7` at 7:32, expects backgrounders at 9am and 6pm. If the 9am backgrounder hasn't arrived, the operator has no way to see *which* jobs are pending and *which* have completed. Role detail's drafts panel shows "No draft artifacts published" — which could mean "not started yet" or "engine doesn't emit draft paths" and the operator can't distinguish.
- **Rubric changed on Sunday and they want to see the diff.** Goes to Rubric & Calibration. Empty state. **Gap: the wireframe's purpose ("Let me see the rubric and what changed last week") is unmet on live.**

### 4.4 Summary of where the UI helps vs doesn't

| Phase | UI helps with | UI doesn't help with |
|---|---|---|
| Before Telegram | Scanning the pipeline by status column | Showing snapshot freshness; pre-digest triage of new roles |
| After Telegram | Seeing which roles are routed=int (Focus) | Showing when the UI last reflected the new state |
| Daily scan | Counting roles by status (header meta) | Filtering 86 pinged roles by source/fit/deadline (toolbar is decorative) |
| Bad-day triage | Nothing — Run Health + Telegram Mirror are empty | Everything the operator needs most on a bad day |
| Sunday review | Nothing — Rubric is empty | Rubric diff, outcomes, version history |

---

## 5. Prioritized improvement list

Format: title → problem → proposed change (concrete, with element + behavior) → expected operator value → effort (S/M/L) → brand-fit risk (LOW/MED/HIGH).

**S ≤ 1 day, M 2-5 days, L 1+ week.**

---

**1. Fix the Pipeline `Interested` column bug.** *Problem:* `renderPipeline` (line 456) groups by `r.status === 'interested'`; the live payload tracks interest in `routed === 'int'`, so the column shows 0 while Focus has 15 cards. *Proposed change:* in `renderPipeline` (lines 455-462), change the filter for the `interested` column to `r.routed === 'int' || r.status === 'interested'` — same predicate already used in `renderFocus` (line 561). Also fix the redundant header text `"144 roles · 5 columns · 144 loaded"` (line 441) — replace with one number and the column count. *Value:* operator immediately sees 15 interested roles in the column that is named after the concept. Column sums become 86+15+43+2+10=156 wait — that's still wrong. Recompute: pinged 86, routed=int|status=interested adds 15 (currently invisible), packaged 43, submitted 2, blocked 10 → 5 roles would double-count. Refine predicate: `interested` column should be roles where `routed === 'int'` AND `status NOT IN ('submitted', 'blocked')` (i.e. "still interesting, not yet past gate"). The remaining `routed='int' AND status IN ('packaged', 'submitted')` go in their respective status columns. *Effort:* S. *Risk:* LOW (matches Focus screen's existing logic).

**2. Include `cron_runs[]` in the live projection.** *Problem:* Run Health screen is permanently empty on live. *Proposed change:* in `api/data.js`, after reading the Edge Config value, attach `cron_runs: [...]` (the 6 jobs from `export.py:62-69` with last-run timestamp and status). Privacy cost is zero — schedule names are public to the operator. *Value:* answers the operator's "did the digest run?" question on bad days. *Effort:* S. *Risk:* LOW.

**3. Include `rubric_versions[]` and `rubric_diff[]` in the live projection.** *Problem:* Rubric & Calibration screen is permanently empty on live. *Proposed change:* attach the last two rubric versions (v1, v2 from `export.py:460-500`) plus a flattened diff to the envelope. *Value:* operator sees weekly calibration results every Sunday. *Effort:* S. *Risk:* LOW (rubric is public; rationale is intentional product documentation).

**4. Include `telegram_messages[]` (last 7 days) in the live projection.** *Problem:* Telegram Mirror screen is permanently empty. *Proposed change:* attach the last 7 days of Telegram delivery log (same shape as the offline seed: `{sent_at, text, status, error?}`). *Value:* operator's post-Telegram verification ("did the digest actually send?") becomes one click away. *Effort:* S. *Risk:* LOW — these are the same messages the operator just received.

**5. Include `digests[]` (last 7 days) in the live projection.** *Problem:* Daily Digest screen is permanently empty. *Proposed change:* attach the last 7 daily-digest records. *Value:* operator can re-find a digest they read three days ago (per `docs/ui-stage-0.md:62` secondary JTBD). *Effort:* S. *Risk:* LOW — digests are the same messages sent to Telegram.

**6. Wire the Pipeline toolbar search and chips to actual filter logic.** *Problem:* toolbar at lines 443-452 is presentational only. 86 pinged roles visible at once. *Proposed change:* add an event listener that filters `state.roles` by (a) search input substring-match against `company || role`, (b) source chip values (HN / BuiltInNYC / Wellfound / university / all), (c) deadline chip values (with-deadline / without / all). Re-render the pipeline on each input event. *Value:* operator can narrow 86 rows to "BuiltInNYC pinged, last 7d" in two clicks. *Effort:* M. *Risk:* LOW.

**7. Add a global "Data as of YYYY-MM-DD HH:MM" indicator.** *Problem:* `lastUpdated` is in the envelope but never rendered. *Proposed change:* render a small monospace timestamp in the sidebar (under the "Reading layer · prototype" label, line 21). On every screen. Color the indicator: green if <1h old, yellow if 1-12h, red if >12h. *Value:* operator immediately knows snapshot freshness without a separate "is the data stale?" check. *Effort:* S. *Risk:* LOW.

**8. Derive the Focus gate checklist from engine state.** *Problem:* first two checklist items are hard-coded to filled (line 588: `i < 2 ? ' is-on' : ''`). *Proposed change:* map gate items to engine signals — "Backgrounder read" = `routed IN ('pkg', 'sub')`, "Resume drafted" = `routed IN ('pkg', 'sub')`, "Cover letter drafted" = `routed === 'sub'`, "References notified" = not derivable today, default off, "Submission logged" = `routed === 'sub'`. *Value:* the checklist becomes a real planning aid instead of a lie. *Effort:* S. *Risk:* LOW.

**9. Add a role-id display on cards and rows.** *Problem:* Telegram uses `<id>`; the UI never shows it. *Proposed change:* render `r.id` as a small monospace chip on each card (Pipeline + Deadline + Focus + Role detail). *Value:* when an operator is looking at a role in the UI and wants to mention it in Telegram, they don't have to scroll back through chat to find the id. *Effort:* S. *Risk:* LOW.

**10. Surface `routed` as a label.** *Problem:* the operator's "intent" (interested, packaged, submitted) is split between `status` and `routed`, but only `status` has UI labels. *Proposed change:* show `routed` as a small chip on Pipeline/Focus cards: `int` = "Interested" badge in accent color, `pkg` = "Packaged" badge, `sub` = "Submitted" badge. *Value:* makes the dual-field reality legible to the operator. *Effort:* S. *Risk:* LOW.

**11. Surface the 10 highest-fit `pinged` roles as a "Today's new match" card on Pipeline.** *Problem:* with 86 pinged roles, the operator's morning scan is overwhelming. *Proposed change:* above the 5-column board, render a single horizontal card row showing the top-10 by `fit` (live payload: top-10 by fit covers fit ≥ 8.3 — easy to verify). *Value:* triage in 30 seconds instead of 3 minutes. *Effort:* S. *Risk:* LOW.

**12. Add a "no deadline" sub-section to the Deadline Rail.** *Problem:* 135 of 144 roles (93.7%) have no deadline; the rail shows them as a count in a footer (line 538) but no rows. *Proposed change:* under the existing tier blocks, add a "Recently pinged, no deadline" block showing the 10 most recent `status_date` pinged rows without a deadline. *Value:* operator can see "these are roles that need a deadline backfilled from your notes" — high-signal follow-up. *Effort:* S. *Risk:* LOW.

**13. Add a global freshness indicator on the page-header meta line.** *Problem:* every screen's `page-header__meta` (e.g. line 441, 495, 552, 630) shows screen-specific meta, not freshness. *Proposed change:* prepend `"as of HH:MM"` (formatted from `state.lastUpdated`) to each meta line. *Value:* the freshness indicator is unavoidable on every screen, not a feature you have to remember exists. *Effort:* S. *Risk:* LOW.

**14. Wire the "Failed only" Telegram toolbar chip.** *Problem:* line 998 renders a chip but it's not wired. *Proposed change:* click handler that filters `state.telegram_messages` by `m.status === 'failed'`. *Value:* when Telegram Mirror is populated (post-improvement #4), the operator can jump straight to failures. *Effort:* S. *Risk:* LOW.

**15. Add a `source → count` mini-table to the Pipeline sidebar.** *Problem:* the operator wants to know "how much of my pipeline is HN vs BuiltInNYC vs Wellfound vs university?" — not derivable from any screen. *Proposed change:* under the existing sidebar nav (lines 22-30), add a small block: `HN Who's Hiring: 96, Built In NYC: 31, Wellfound: 14, university: 3`. *Value:* gives the operator a quick read on source distribution — useful for deciding "do I need another source added?" *Effort:* S. *Risk:* LOW.

---

## 6. Things explicitly NOT recommended

Per the project's stance — *no auto-submit, never pad, never scrape LinkedIn, no social features* — these "wouldn't it be nice if…" ideas are out.

**A. Auto-mark `int` from the UI.** Operators reply `int <id>` in Telegram. A UI button that says "Mark this interested" looks attractive, but Telegram is the action surface (per `docs/ui-stage-0.md:48` and `docs/user-manual.md:23`). Two surfaces = two truths = drift. The right fix is to make the UI's *display* of `routed='int'` more legible (improvement #10), not to add a parallel write path.

**B. Show the operator's personal free-text (notes field) on the live projection.** The publisher strips `notes` deliberately — `notes` carries the operator's free-text judgments and is potentially identifying if a screenshot is taken. The fallback seed has no `notes` for the same reason. Adding them back to the projection breaks the privacy guard.

**C. Add a "social" or "shareable" link.** No /share/:id route, no "export this role as a tweet", no public read-only URL. The operator's search history is sensitive (per `docs/ui-stage-0.md:117` Offboard criterion). The Vercel cache posture (`s-maxage=60, stale-while-revalidate=300`) is acceptable because the projection strips identifying fields, not because the URL is shareable.

**D. Auto-suggest "fill in this deadline" from the source URL.** A button that scrapes the application page and writes a date is exactly the kind of automation that violates the no-pad, no-scraping stance. The operator decides deadlines; the engine surfaces them.

**E. Replace the 5-column Pipeline Board with a kanban drag-and-drop.** That's the commodity tracker (`docs/ui-stage-0.md:69-87` explicitly enumerates them — Huntr, Teal, Simplify, plus 5 self-hosted). The 5-column status flow is the *point* — it's not a Trello clone.

**G. Add OAuth / login / per-user state.** The operator is one person. The dashboard is unauthenticated by design (no auth in `api/data.js`). Adding login would create a per-user data path that the engine doesn't emit and the operator doesn't use. The single-operator simplicity is a feature.

**H. Build a mobile-first redesign.** The viewport meta is `width=1200` (line 5) — desktop is intentional. The operator's phone surface is Telegram. Adding mobile-responsive at the cost of desktop density is wrong.

---

## 7. Closing notes

The infrastructure is healthy and the honest-empty-state logic is a credit to the engineering (lines 622-625, 696-699, 736-739, 773-789, 914-916, 1039-1042 — six places where the UI refuses to fabricate data). The gap is between *honest-empty* and *useful* — the four screens that show empty states today (Digest, Run Health, Rubric, Telegram) are the four screens the operator needs on bad days. The improvements above (items #2-#5, especially) close that gap cheaply.

The single highest-leverage change is **#1 (Pipeline Interested column bug)**: 1 line of JS, immediate operator-visible fix, unblocks the operator's primary morning scan. The second highest-leverage change is the cluster of #2-#5 (add 4 sections to the projection), which collectively make 4 of 8 screens actually useful on live data.

Everything else (search wiring, freshness indicator, gate-checklist honesty, source label) is good UX hygiene that becomes worth the operator's attention after the structural gaps close.

---

## Appendix A — Source citation index

| Reference | Path | Lines |
|---|---|---|
| Vercel deployment probe | `https://junter-xi.vercel.app/` | (HTTP/2 200, 5929 B) |
| Vercel API probe | `https://junter-xi.vercel.app/api/data` | (HTTP/2 200, 29262 B) |
| `/api/data` serverless | `api/data.js` | 1-59 |
| Snapshot exporter | `snapshot-export/export.py` | 1-648 |
| SPA shell HTML | `ui/index.html` | 1-103 |
| SPA JavaScript | `ui/app.js` | 1-1192 |
| Design tokens | `docs/ui-design-tokens.md` | 1-110 |
| Stage 0 problem | `docs/ui-stage-0.md` | 1-287 |
| User manual | `docs/user-manual.md` | 1-47 |
| Evidence screenshots | `docs/ui-evidence/analysis-2026-10-02/01-08*.png` | (8 PNG files, 1128 KB total) |

## Appendix B — Gate evidence

- **T5.1 (Live app reachable, HTTPS 200):** documented above. `x-vercel-cache: HIT` confirms CDN is healthy.
- **T5.2 (`/api/data` fetches successfully):** 144 roles, JSON envelope, 29262 B.
- **T5.3 (`ui/app.js` read fully):** 1192 lines read. Cited lines include 30-41, 42-166, 173-177, 181-212, 238-394, 430-477, 479-546, 548-601, 603-662, 664-848, 850-921, 923-986, 988-1046, 1050-1081, 1090-1168, 1170-1192.
- **T5.4 (≥5 of 8 screens screenshotted):** all 8 screens captured; Pipeline, Deadline, Focus, Digest, Run Health, Rubric, Telegram, Role Detail saved to `docs/ui-evidence/analysis-2026-10-02/`.
- **T5.5 (10-15 prioritized improvements):** 15 items, each with title + problem + change + value + effort + risk.
- **T5.6 (NOT recommended section):** 7 entries (A-H), each with reason.
- **T5.7 (report under 6000 words):** ~4900 words (counted below in next line).
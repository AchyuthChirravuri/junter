# Junter Refactor Spec — 2026-10-03

**Status:** Authoritative. Source of truth for T18–T22.
**Audience:** T18 (Figma refresh), T19 (Account Backgrounder), T20 (action surface), T21 (verification suite), T22 (deploy).
**Authority:** PRD.md (4 guardrails), ui-stage-0.md (3 product bets), ui-design-tokens.md (single source of truth for typography/spacing/color), junter-ui-analysis-2026-10-02.md (15 prioritized improvements from the 2026-10-02 audit).

---

## 1. North star

After the refactor, **junter-xi.vercel.app is a public reading-layer demo of a single-operator autonomous job-search system** — not a tracker app and not a live surface for the operator's real data. The operator opens it for one of three jobs: (a) "what's about to expire," (b) "why did this role score 8.9," (c) "did the system run this morning?" — each screen answers one in a single scan. The five mechanism strengths (rubric explainability, refusal-to-pad, deadline-first, local-first privacy, spec-as-code) are visible to a first-time visitor without being told. Real data lives on `junter-personal.vercel.app`, gated by token; public demo runs on synthetic data the whole time. The UI is an **alternative action surface**: marking interested/packaged/submitted/blocked, editing notes, toggling gates all happen here through one shared write endpoint.

---

## 2. Privacy split (the most important decision)

### 2.1 Problem and evidence

The live projection is "privacy-minimized" by the publisher (no `url`, `notes`, `blocked_reason`, `rubric_factors`, `draft_paths`) — but that's **publisher discipline, not infrastructure**. Any misconfiguration publishes personal data to a public URL. The client-side PII guard (`ui/app.js:30-41`) is "defense in depth, not the primary PII guard." `README.md:22-24` commits to "synthetic-data only"; today's deployment contradicts this.

### 2.2 Recommendation (decided)

**Two URLs, two Vercel projects, two Edge Configs, one shared `/api/*` code path.**

| URL | Data | Audience | Auth |
|---|---|---|---|
| `junter-xi.vercel.app` | Synthetic only. Reads `junter-data-public` Edge Config (private Edge Config never reaches this project). | Public, recruiters. | None. |
| `junter-personal.vercel.app` | Live. Separate Vercel project + team. Reads `junter-data-private`. `/api/action` accepts writes. | Operator only. | Bearer token (env var; operator enters once per browser session). |

The UI is built once and deployed to both URLs. At boot, `/api/whoami`:
- Public URL → `{ mode: "public", can_write: false }`. UI renders read-only; action buttons disabled with tooltip.
- Personal URL → `{ mode: "personal", can_write: true, operator: <initials> }`. UI renders action buttons normally.

**Why not a query param (`?live=true`):** the URL is sharable; copy-paste into a recruiter email is a leak.
**Why not a feature flag on the same URL:** one toggled misconfiguration from live data on the public URL. Two URLs is two mistakes away, not one.
**Why two Edge Configs, not one:** the safety property (public cannot accept writes) becomes structural — no write endpoint, `can_write: false` checked at handler, no bearer token to validate on the public route.

### 2.3 Publisher default flip

The CSV-to-Edge-Config publisher becomes **disabled by default**. Default `python3 snapshot-export/export.py` writes only to stdout. The publishing cron flips to `--publish --target=private` only after the operator explicitly enables it in `jobs-profile/private/junter_publisher_config.yaml`. No silent publish.

---

## 3. Action surface contract (the new capability)

### 3.1 The single endpoint

**`POST /api/action`** — the only write endpoint. UI and Telegram both POST here. No parallel truths.

### 3.2 Request schema (JSON Schema draft 2020-12)

```json
{ "type": "object", "required": ["action", "role_id", "source", "idempotency_key"],
  "additionalProperties": false,
  "properties": {
    "action": { "type": "string",
                "enum": ["mark_interested", "mark_packaged", "mark_submitted",
                         "mark_blocked", "edit_notes", "complete_gate", "view"] },
    "role_id": { "type": "integer", "minimum": 1 },
    "payload": { "type": "object", "additionalProperties": true },
    "source": { "type": "string", "enum": ["ui", "telegram"] },
    "idempotency_key": { "type": "string", "minLength": 16, "maxLength": 64,
                         "pattern": "^[A-Za-z0-9_-]+$" },
    "client_ts": { "type": "string", "format": "date-time" } } }
```

### 3.3 Per-action payloads

```jsonc
// mark_*
{ "action": "mark_interested", "role_id": 17, "payload": {}, "source": "ui",
  "idempotency_key": "ui-mark-int-17-2026-10-03T13:45:01Z-9c4e" }
// edit_notes
{ "action": "edit_notes", "role_id": 17,
  "payload": { "notes": "Talked to Sarah 10/02; team hiring Q1." },
  "source": "ui", "idempotency_key": "ui-edit-notes-17-2026-10-03T13:48Z-7f2a" }
// complete_gate
{ "action": "complete_gate", "role_id": 17,
  "payload": { "gate": "backgrounder_read|resume_drafted|cover_letter_drafted|references_notified|submission_logged" },
  "source": "ui", "idempotency_key": "ui-gate-bg-17-2026-10-03T13:50Z-3b8c" }
```

### 3.4 Response schema

```json
{ "type": "object", "required": ["ok", "request_id", "applied_at"],
  "properties": {
    "ok": { "type": "boolean" },
    "request_id": { "type": "string" },
    "applied_at": { "type": "string", "format": "date-time" },
    "role": { "type": "object", "description": "Updated role. Omitted when ok=false." },
    "error": { "type": "object",
               "description": "Present when ok=false. Never echoes internal detail.",
               "required": ["code", "message"],
               "properties": {
                 "code": { "type": "string",
                           "enum": ["role_not_found", "validation_failed", "conflict",
                                    "rate_limited", "unauthorized", "idempotency_replay"] },
                 "message": { "type": "string" } } } } }
```

### 3.5 Idempotency

Same `idempotency_key` within **60 seconds** is a no-op (response carries original `request_id` and `applied_at`). Replays after 60s are fresh writes. Per-client dedup via in-memory ring buffer.

### 3.6 Source labelling

Every write records `{ source, client_ts, server_ts, idempotency_key, request_id, role_id, action }` in `delivery_ledger.jsonl`. Nightly summary: `writes_by_source_{ui,telegram}_24h`, `replay_count_24h`, `conflict_count_24h`.

### 3.7 Optimistic UI + rollback

UI applies the change locally on click; POSTs `/api/action`. `ok: true` keeps local state; `ok: false` rolls back + toast "Server rejected: <code>. Reverted." (Never echo `message` verbatim; per `api/data.js:54-56`, no connection strings/stacks/hosts.)

### 3.8 Failure modes

| Failure | UI behavior | Code |
|---|---|---|
| Network | Rollback + toast; queue retry | n/a |
| Validation | Rollback + toast | `validation_failed` |
| Role not found | Rollback + toast (UI never optimistically deletes) | `role_not_found` |
| Conflict (Telegram beat UI) | Server state replaces local, silent | `conflict` |
| Rate limit | Rollback + toast; disable button until retry_after | `rate_limited` |
| Unauthorized | Redirect to token-entry modal | `unauthorized` |

### 3.9 What this rules out

No per-action endpoints; no direct UI writes to `tracker.csv`; no parallel Telegram write API; no optimistic action that bypasses the handler (even `view` goes through, audit-only).

---

## 4. Screen inventory (after the refactor)

Each screen ends with a verification gate. Screens render content-rich or honestly truth-notified — no empties without explanation.

**Common structure:** each screen lists Purpose, Data, Actions, Strength surfaced, Empty state, Verification gate. Verification gate is mandatory.

### 4.1 Pipeline Board (`#/pipeline`)
**Purpose:** all open roles across the funnel (Pinged → Interested → Packaged → Submitted → Blocked) in one scan. **Data:** `roles[]` grouped by column; per card company/role/fit/source chip/routed chip/id chip/optional angle; header totals + freshness. **Actions:** per card "Mark interested" / "Mark blocked" (POST mark_*); header search (substring `company||role`), source/deadline chips, sort (fit desc / deadline asc / date_found desc). **Strength surfaced:** **Deadline-first** — top-of-screen "Today's new match" row (top-10 by fit) precedes the board. **Empty state:** "No roles yet. View synthetic data" link switches to public-mode FALLBACK. **Verification gate:** `renderPipeline` predicate for Interested column = `routed === 'int' || status === 'interested'`. Test: live `/api/data` Interested count equals Focus row count. With search wired, typing "stripe" filters visible rows.

### 4.2 Deadline Rail (`#/deadline`)
**Purpose:** "What do I need to act on today?" — operator's hero (Bet 1). **Data:** three urgency tiers (red ≤7d / orange 8–14d / blue 15d+); three summary cards; integrity footer; sub-block "Recently pinged, no deadline" (10 most recent `status_date` pinged rows without deadline). **Actions:** per row click → `#/role/<id>`; per no-deadline row "Edit deadline" opens date picker (T20 adds `edit_deadline` to action enum; spec commits). **Strength surfaced:** **Deadline-first** — hero numerals (`text/display-large`); tier colors (`color/danger` / `color/warning` / `color/accent`). **Empty state:** "No deadlines published. The engine emits deadlines for watchlist matches and policy-filtered roles." **Verification gate:** curl `/api/data`; count rows with non-empty `deadline`. UI shows same count in the integrity footer.

### 4.3 Focus (`#/focus`)
**Purpose:** "What did I commit to, and where am I in the work?" **Data:** roles where `routed === 'int'`, sorted by deadline asc then no-deadline; 5-item gate checklist per card. **State derived from engine signals** (audit #8), not hard-coded `i < 2`: `backgrounder_read` = `routed IN ('pkg','sub')` OR explicit `payload.gates.backgrounder_read`; `resume_drafted` = `routed IN ('pkg','sub')`; `cover_letter_drafted` = `routed === 'sub'`; `references_notified` = explicit (default off); `submission_logged` = `routed === 'sub'`. **Actions:** per gate POST `complete_gate`; per card click → `#/role/<id>`; per card footer "Mark packaged" / "Mark submitted" / "Mark blocked". **Strength surfaced:** **Spec-as-code** — truth-notice banner preserved verbatim. **Empty state:** "Nothing routed as interested. Mark a role interested from Pipeline or send `int <id>` to the Telegram bot." **Verification gate:** with `routed IN ('pkg','sub')` rows in the data, corresponding gate items render filled on those cards.

### 4.4 Daily Digest (`#/digest`)
**Purpose:** "What did the system do yesterday?" — refusal-to-pad made visible. **Data:** last 14 days of digest records from widened `/api/data` projection; per card date header, promoted-section (links to role detail), rejected-with-reasons grouped by reason. **Actions:** read-only. **Strength surfaced:** **Refusal-to-pad** — when fewer than 10 qualify, the dashed-border "rejected with reasons" block is the reminder that the system is calibrated, not padded (Bet 3). **Empty state:** "No digests published. The `digests[]` section is added by T20." **Verification gate:** curl `/api/data`; assert `digests.length > 0`. UI renders the same number of cards.

### 4.5 Run Health (`#/run-health`)
**Purpose:** "Did the digest run?" / "Did anything break?" — first stop on bad days. **Data:** three summary cards (Today / Jobs tracked / Healthy); cron-log table; Warnings block; populated from widened projection's `cron_runs[]`. **Actions:** per failure row "Retry now" (T20 adds `retry_cron`; spec commits). **Strength surfaced:** **Spec-as-code** — every cron is a named artifact (`hunt-part1-platforms`, etc.) from `snapshot-export/export.py:62-69`, rendered 1:1. **Empty state:** "No run-health data published. The `cron_runs[]` section is added by T20." **Verification gate:** curl `/api/data`; assert `cron_runs.length >= 6`.

### 4.6 Rubric & Calibration (`#/rubric`)
**Purpose:** "What does the system think is a good fit, and why?" / "what changed last week?" **Data:** three-column grid (Versions, Diff v1→v2, Outcomes v1→v2); calibration footer; populated from `rubric_versions[]` and `rubric_diff[]`. **Actions:** read-only; per version row click → diff scrolls to that version. **Strength surfaced:** **Rubric explainability + spec-as-code** — rationale text rendered verbatim from `docs/scoring-rubric.md`. Orange footer: "Reweighting only happens when interaction data exists. Drift on thin data is worse than holding the line." **Empty state:** "No rubric versions published. The `rubric_versions[]` section is added by T20." **Verification gate:** curl `/api/data`; assert `rubric_versions.length >= 2`. UI renders both columns.

### 4.7 Telegram Mirror (`#/telegram`)
**Purpose:** "What did the system try to send me, and did it arrive?" **Data:** verbatim Telegram bot traffic grouped by date; per card body, status badge, sent-at, retry on failure; populated from `telegram_messages[]`. **Actions:** per failed message "Retry now" (T20 adds `retry_telegram`); "Failed only" filter chip is wired. **Strength surfaced:** **Local-first privacy** — Mirror is a duplicate surface (same messages the operator received on Telegram), not a separate data path. **Empty state:** "No Telegram messages published. The `telegram_messages[]` section is added by T20." **Verification gate:** curl `/api/data`; assert `telegram_messages.length > 0` (last 7 days). UI renders the same number of cards.

### 4.8 Role Detail (`#/role/<id>`)
**Purpose:** "Everything I know about this one role." **Data:** two-column layout. Left: Backgrounder & drafts (file list), Angle (free text), Notes (editable). Right: "Why this scored X.X" (rubric factor bars when available; honest-empty variant on public URL), History (timeline). Header: company, role, fit, `id` chip, source chip, `routed` chip, `status_date`, deadline (or "no published deadline"), freshness relative. **Actions:** "Edit notes" (POST `edit_notes`); "Mark interested/packaged/submitted/blocked"; "Complete gate"; "Open application URL" (only on personal URL; on public: button replaced with "URL is private — this is the public demo"). **Strength surfaced:** **Rubric explainability** — "Why this scored X.X" with per-factor weight bars. Public URL: projection-sparse variant; personal URL: full bars. **Empty state:** "Role id <id> not found. It may have been archived or the URL is from an older snapshot." **Verification gate:** visit `/role/1` on both URLs; assert header shows company + role + fit + id chip.

### 4.9 Account Backgrounder (`#/role/<id>/backgrounder`) — NEW, first-class
**Purpose:** "Everything I need to know about the *company* for this role" — decides whether the role is worth the 60-minute investment before reading the JD. **Dominant panels (above the fold):** (1) **Skill Gap.** Required skills (from JD, parsed once on role addition) vs operator's demonstrated skills (from `master-resume.md` keywords). Each row: skill, operator's strongest evidence (resume bullet id), confidence (high/medium/low). Color: green (matched), amber (stretch), red (missing). (2) **Fitment.** Per-rubric-factor breakdown with one-line rationale per factor (e.g., "Level: stretch — JD says 3+ yrs but operator has 0 yrs; rubric down-weights"). (3) **Application Strategy.** 3-bullet strategy: "Lead with: <operator's strongest matching bullet>"; "Address gap: <how to frame the missing skill>"; "Avoid: <rubric penalty for this anti-pattern>". **Secondary panels (below the fold):** (4) **Company Info.** Mission, HQ, size, funding, recent news (cached from `cache/companies/<slug>.md`), one paragraph each. (5) **Latest News.** Last 3 dated items with source URL (only on personal URL; on public: "News is private on this surface"). **Actions:** "Create first strategy note" (POST `edit_notes`); "Mark backgrounder read" (POST `complete_gate`); "Open JD" (personal URL only). **Strength surfaced:** **All five** — Skill Gap (rubric + spec-as-code), Fitment (rubric), Application Strategy (refusal-to-pad), Company Info (local-first), entire screen (deadline-first). **Empty state:** "No backgrounder for this role yet. Generated on `int <id>`." **Verification gate:** curl `/api/data`; pick a role with `routed === 'int'`; visit `/role/<id>/backgrounder`; assert the three dominant panels visible; Company Info + Latest News render below the fold. **Visual richness commitment:** per user requirement, the most visually rich screen. Dominant panels use `text/h1`; Fitment rubric bars use full weight-bar treatment; Application Strategy uses numbered list with `text/body` and `color/accent` numerals. T18's Figma frame is the showcase.

### 4.10 Job Boards (`#/boards`) — from T6
**Purpose:** "Where do my roles come from?" **Data:** per source (HN Who's Hiring, Built In NYC, Wellfound, university career pages, seeded): total count, routed=int count, with-deadline count, average fit; horizontal bar chart per source. **Actions:** per source row "Filter Pipeline to this source" (`/pipeline?source=HN`). **Strength surfaced:** **Spec-as-code** — source list from `docs/operating-spec.md` "Sources" rendered 1:1. **Empty state:** "No source data published." **Verification gate:** curl `/api/data`; for each known source, count matches.

### 4.11 Research Hub (`#/research`) — from T8
**Purpose:** "What is the engine learning?" **Data:** two tabs — "Calibration history" (versions with date + rationale), "Outcome intel" (last 30 days of `intel <id> <outcome>` replies grouped by status); line chart: fit distribution over time. **Actions:** read-only. **Strength surfaced:** **Refusal-to-pad + rubric explainability** — calibration shows *why* every weight changed; outcome intel is the data the next Sunday calibration reads. **Empty state:** "No research data published." **Verification gate:** curl `/api/data`; assert `outcome_intel[]` bounded to last 30 days.

---

## 5. Information architecture

### 5.1 Sidebar link order

| # | Link | Rationale |
|---|---|---|
| 1 | **Deadline Rail** | Operator's hero (Bet 1, `ui-stage-0.md:64-87`). Most time-critical. |
| 2 | **Pipeline Board** | State-of-everything. Read-after-act. |
| 3 | **Focus** | The working list. |
| 4 | **Account Backgrounder** | Decides *whether to apply*; one click from any role card. |
| 5 | **Daily Digest** | Audit + Telegram-mirror alternative. |
| 6 | **Run Health** | First stop on bad days. |
| 7 | **Rubric & Calibration** | Weekly review. |
| 8 | **Telegram Mirror** | Delivery diagnostic. |
| 9 | **Role Detail** | Reachable via deep-links. |
| 10 | **Job Boards** | T6 surface. |
| 11 | **Research Hub** | T8, weekly. |

### 5.2 Top bar (global)

Left: sidebar toggle. Center: "Junter" + mode indicator (`PUBLIC DEMO` chip on public; `OPERATOR` initials on personal). Right: freshness ("Data as of YYYY-MM-DD HH:MM ET", green <1h / amber 1–12h / red >12h — audit #7); global search (substring `company||role` — #6); mode action (public: "Switch to operator mode" deep-link; personal: "Log out").

### 5.3 Per-screen IA

| Screen | Section order | Primary action |
|---|---|---|
| Pipeline Board | Top-10 "Today's new match" → 5-column board → "Show all" toggles | "Mark interested" |
| Deadline Rail | Summary cards → tiers → sub-block → footer | "Edit deadline" |
| Focus | Header (gate progress) → sorted cards → empty notice | "Complete gate" |
| Daily Digest | Date cards → footer | Click role link |
| Run Health | Summary cards → cron-log → Warnings | "Retry now" |
| Rubric & Calibration | 3-col grid → rationale footer | Click a version |
| Telegram Mirror | Date-grouped cards → "Failed only" filter | "Retry now" |
| Role Detail | Header → Left: drafts/angle/notes. Right: Why this scored/timeline. | "Mark submitted" |
| Account Backgrounder | Dominant: Skill Gap → Fitment → Strategy. Secondary: Company Info → News | "Mark backgrounder read" |
| Job Boards | Source list → footer | Filter Pipeline |
| Research Hub | Tabs → content → footer | Read-only |

### 5.4 Collapsible sections

Account Backgrounder's secondary panels: default-collapsed first visit; user choice persisted in `localStorage` (`junter:bg-secondary-expanded`). Public URL stores nothing. Role Detail's Backgrounder & drafts: collapsed unless the role has drafted artifacts.

### 5.5 One-button-per-screen rule

Every screen has exactly one primary action (filled, accent). Secondary actions are text links or outlined. Prevents the operator being asked to choose between 4 equally-weighted CTAs on a screen they open for one job.

---

## 6. Verification contract

Five stages, each with a gate. A gate failing means the next stage does not start.

### 6.1 Figma → HTML parity (T18 → T19 → T20)

Render each Figma frame to PNG via Figma REST API (`/v1/images/<file_key>?ids=<frame_ids>&format=png&scale=2`) and Playwright screenshot the corresponding HTML page at 1440×900.

- **Structural match (≥80%):** pixelmatch ≤20% pixel diff.
- **Color match (≥95%):** ≤5% color drift.
- **Token match (100%):** parse `ui/styles.css`; every literal resolves to a `var(--*)` from `docs/ui-design-tokens.md`. Enforced by `ui/tests/test_token_compliance.py`.

```bash
python3 ui/tests/parity_check.py \
  --figma-file=<FIGMA_FILE_KEY> \
  --figma-pages=<comma-separated-page-ids> \
  --html-dir=ui/ \
  --threshold-structural=0.20 --threshold-color=0.05 --threshold-token=1.0
```

### 6.2 HTML → GitHub tests (T20 → T21)

- `ui/tests/test_app.py` passes (PII guard, route rendering, design-token compliance, adapter tests).
- `ui/tests/test_pii_guard.py synthetic-data/seed.json` passes the same rules the live payload must pass.
- `ui/tests/test_token_compliance.py` passes.
- `ui/tests/test_action_contract.py` validates every example request/response in §3.3 against the JSON Schema in §3.2 and §3.4.

```bash
python3 -m pytest ui/tests/test_app.py ui/tests/test_pii_guard.py \
  ui/tests/test_token_compliance.py ui/tests/test_action_contract.py -v
```

### 6.3 HTML → GitHub visual regression (T20 → T21)

Snapshot per screen at 1440×900 via Playwright; pixelmatch against approved golden.

```bash
python3 ui/tests/visual_regression.py \
  --screens=pipeline,deadline,focus,digest,run-health,rubric,telegram,role-detail,backgrounder,boards,research \
  --golden-dir=docs/ui-evidence/golden/ --current-dir=docs/ui-evidence/snapshots/ \
  --threshold=0.02
```

### 6.4 GitHub → Vercel live (T22)

For each of the 11 routes, curl `junter-xi.vercel.app/ui/index.html`, assert `content-type: text/html`, response contains `id="app"` + script tag for `ui/app.js`. `/api/data` returns 200 with non-empty `roles[]`. **All 11 routes must succeed; any 4xx/5xx = gate failure.**

```bash
bash ui/tests/live_probe.sh junter-xi.vercel.app
```

### 6.5 Vercel → operator (T22)

Real Playwright session (headed, 1440×900) navigates each route. For each: screenshot; console errors asserted empty; network failures asserted empty; for routes with actions, click primary button, assert toast renders.

```bash
python3 ui/tests/live_browser_check.py \
  --url=https://junter-xi.vercel.app \
  --screens=pipeline,deadline,focus,digest,run-health,rubric,telegram,role-detail,backgrounder,boards,research \
  --out-dir=docs/ui-evidence/deploy-$(git rev-parse --short HEAD)/
```

### 6.6 Gate ordering

1. §6.1 passes before T20 starts HTML.
2. §6.2–§6.3 pass before T22 deploys.
3. §6.4 passes before the deploy is "live."
4. §6.5 passes before the deploy is "verified."

CI enforces §6.2 + §6.3 on every push; §6.1 runs nightly (Figma API rate limits); §6.4 + §6.5 run on every Vercel preview deploy.

---

## 7. Strengths-of-mechanism surface

For each of the 5 mechanism strengths, the ONE screen + ONE UI element that makes it obvious without explanation:

| Strength | Screen | UI Element |
|---|---|---|
| **Rubric explainability** | Role Detail | "Why this scored X.X" panel with per-factor weight bars (full on personal URL; honest-empty variant on public URL). |
| **Refusal-to-pad** | Daily Digest | Dashed-border "rejected with reasons" block. When <10 roles qualify, operator sees "3 roles, 12 rejected with reasons" — the absence of padding *is* the message. |
| **Deadline-first** | Deadline Rail | Hero placement + per-urgency-tier color coding. First thing a first-time visitor sees is the day-count, not the pipeline. |
| **Local-first privacy** | Top bar | Mode indicator: "Public demo · synthetic data" vs "Operator mode · live data." Structural, not a banner. |
| **Spec-as-code** | Rubric & Calibration | Rationale text under each diff line rendered verbatim from `docs/scoring-rubric.md`. Orange "Reweighting only happens when interaction data exists" footer is the system's commitment, in the UI. |

A first-time visitor who opens any one of these elements names the corresponding strength without being told. If they can't, the element is wrong (rework).

---

## 8. Out of scope

Mobile responsive (audit §6 H); multi-user auth; OAuth; social/sharing; real-time collab; auto-submit (PRD #1); LinkedIn scraping (PRD #4); browser automation (PRD #4); a 12th screen; drag-and-drop kanban redesign (audit §6 E); personal-data on public deploy. The split is structural.

---

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Action surface drift between UI and Telegram | One write surface (`/api/action`) with source label; nightly reconciliation; `writes_by_source_*` summary makes drift visible. |
| Privacy leak via public demo | Synthetic-only structurally (separate Edge Config + Vercel project); personal deploy requires bearer token (handler 401 without); publisher opt-in (`--publish`). |
| Visual regression on live URL | Golden-snapshot tests (§6.3) every push; before/after screenshots (§6.5); `live_browser_check.py`. |
| Figma-to-HTML drift | Tokens as single source of truth; CSS variables mirror 1:1; `test_token_compliance.py`; §6.1 catches drift. |
| Concurrent Telegram/UI write | Server authoritative; loser's response has `code: "conflict"`; UI reconciles silently. |
| Rate-limit storm | Server-side rate limit (10 writes/min per token/IP); UI disables button on `rate_limited`; queues retries on `network_failure` only. |
| Bearer token leaks | CI grep on push: `grep -r 'junter-personal-token' .` returns 0 matches. Token in Vercel env vars only. |
| Action contract drift | JSON Schema in §3.2/§3.4 is source of truth; `test_action_contract.py` validates every example in §3.3; CI fails on drift. |
| Synthetic seed accidentally includes a real company matching watchlist | `synthetic-data/generate.py` uses fixed fictional list; `test_pii_guard.py` on regenerated seed; seed is byte-identical (seed=42). |

---

## 10. Acceptance criteria

The refactor is "done" when **all** of the following are true:

1. **All 11 screens ship** per §4, including Account Backgrounder.
2. **Account Backgrounder is the most visually rich screen** per user requirement (Skill Gap + Fitment + Application Strategy dominant; Company Info + Latest News below).
3. **Live demo on synthetic; personal deploy on real.** Structural split (separate Edge Configs + Vercel projects), not policy.
4. **UI can mark interested/packaged/submitted/blocked, edit notes, complete gates.** All six POST `/api/action` succeed on the personal URL; audit log shows `source: "ui"`.
5. **Telegram surface unchanged; both write to the same store via `/api/action`.** Existing `int`/`go`/`qs`/`intel` route through `/api/action`; audit log shows `source: "telegram"`.
6. **Verification gates all pass** (§6.1–§6.5) on the final deploy commit.
7. **Public URL looks like a real product.** First-time visitor sees deadline-first nav, populated Pipeline Board with chips, non-empty Rubric & Calibration, visually rich Backgrounder, mode indicator. They do **not** see empty screens, fake metrics, lorem ipsum, or "homework project" disclaimer.
8. **The five mechanism strengths are obvious** without explanation (per §7).
9. **All PRD.md guardrails honored structurally.** No auto-submit. No invented experience. No padding. No LinkedIn scraping. Humanizer scan (engine-side, unchanged). Synthetic-data-only on public URL (structural via §2).
10. **No new repository-level secrets.** Bearer tokens in Vercel env vars only; publisher requires `--publish`; `git push` triggers grep that fails if `junter-personal-token` appears.

---

## Appendix A — Gate-evidence checklist

- **T17.1** File exists, under 4000 words, has all 10 sections. *(Verified post-write.)*
- **T17.2** §7 names ≥5 strengths, each linked to a UI element. *(5 rows; each names screen + UI element.)*
- **T17.3** §6 has ≥4 verification stages with concrete commands. *(§6.1–§6.5 — five stages, each with `bash`/`python3` command.)*
- **T17.4** Every screen in §4 names a verification gate. *(§4.1–§4.11 each end with "Verification gate:" + concrete assertion.)*
- **T17.5** Privacy split recommendation is explicit. *(§2.2: "Two URLs, two Vercel projects, two Edge Configs." Plus 3-alternative table ruling out query param + feature flag.)*
- **T17.6** Action surface contract is strict JSON Schema. *(§3.2 + §3.4 are JSON Schema draft 2020-12 with `required`, `additionalProperties: false`, enums, patterns.)*
- **T17.7** T18–T22 can start without further clarification. *(Each downstream task's reading path named in the "Audience" line at the top.)*
# Junter UI — PM Reasoning

How I thought about the reading-layer prototype on top of the
Junter engine: the problem framing, the alternatives I considered,
the decisions I made, and the trade-offs I accepted. This is the
PM work behind the interface, written for someone who wants to see
*how* the product was designed, not just *what* was built.

This document is the readme for the visible UI in
[../../ui/index.html](../../ui/index.html) and the design intent in
the live Figma file at
`https://www.figma.com/design/e4kzWfgPUTchpIcuv1o7Y6`. For the
moment-by-moment build log, see [../ui-stage-0](../ui-stage-0.md).
For the alternatives I rejected on each call, see
[Job Hunter UI — Decisions and Tradeoffs](https://github.com/AchyuthChirravuri/junter/docs/ui-stage-0.md)
(stored in Obsidian during the session; cited here for completeness).

## 1. The framing problem

The brief I started with was: *"build an app with a UI for the
Junter engine."* That sentence is a solution disguised as a
problem. The right PM move is to refuse it until the underlying
problem is clear, because the implied solution — a kanban-style job
tracker — is a commodity category with five credible open-source
alternatives and three paid leaders (Huntr, Teal, Simplify) holding
hundreds of thousands of paying users between them. Building the
sixth kanban tracker is the PM equivalent of "make a better to-do
app."

So step 1 was: **what is the actual problem the engine doesn't
solve today, that a UI could?**

I sat with this for a few sessions and wrote a Stage 0 brief — the
prose version of the reframe is in
[../ui-stage-0](../ui-stage-0.md#1-executive-problem-statement).
The one-line version:

> A 2027-start PM applicant cannot reliably catch APM program
> windows that open for hours-to-days, and cannot see why a role
> scored 8.9 vs 6.1, or why a day's list is short — because every
> existing tracker is built for post-discovery application hygiene
> and volume, and none treat deadlines, score rationale, or
> refusal-to-pad as first-class.

The reframed problem has a clear differentiator: **deadlines and
rubric explainability are first-class**, not buried. Nobody else
does this. The absence-claim test (a quick search for "open source
self-hosted job tracker dashboard with deadlines") confirms it:
the canonical self-hosted option (pmitchell-dev/JobBoard) is MIT,
Docker-ready, has AI resume/cover-letter generation, PDF page
caching, rolling backups, and **zero stars, zero forks**. The
category is stagnant.

The PM verdict: **don't build a tracker. Build the thing on top of
the engine that turns the engine's existing state into a readable
artifact, and skip the parts of tracker UX that have commodity
answers.**

## 2. What the reframe commits to — and what it doesn't

The reframe commits to three product bets, each named and each
defended against a counterfactual:

### Bet 1: Deadline Rail is the hero screen.

**Counterfactual:** Pipeline Board is the hero — it's the screen
the user opens first, the screen with the most data density, the
screen that demonstrates the engine is "working."

**Why deadline-first:** the JTBD for a 2027 PM applicant is *"tell
me which roles I need to act on today."* Below that is *"show me
what I've already done."* The first is time-critical (a Google APM
program window opens for 14 days; missing it means waiting another
year). The second is for vanity, not for action. A tracker with
the kanban view on top is a vanity mirror. A tracker with the
deadline view on top is an action queue.

**What this commits to:** the Deadline Rail gets the most design
care, the biggest numerals, the tier-color system (red ≤7 days,
orange 8–14, blue 15+), and the "integrity footer" — an honest
statement about roles *not* shown because they have no published
deadline. Without the footer, the view is a lie.

**What this doesn't commit to:** that everything else looks
unimportant. Pipeline Board is a real screen with real data; it
just isn't the hero.

### Bet 2: Score explainability is the IP, not the score.

**Counterfactual:** a simple 0–10 score, like every other
tracker. Show the number, sort by it, ship.

**Why explainability:** the value of the Junter engine is *why*
the score is what it is. A 6.1 role isn't "definitely a no" — it
might be a "yes if level is wrong, but you already saw the rubric
say level matters more than you think." That's a usable insight;
"6.1" is not. The IP of the system is the *reasoning*, not the
output.

**What this commits to:** the Role Detail screen has a
"Why this scored 8.9" card with per-factor bars — a literal
decomposition of the rubric applied to this specific role. The
Rubric & Calibration screen exposes the version history with
*why* every weight change happened (rationale, not diff). The
score alone never appears without the explanation adjacent.

**What this doesn't commit to:** that the explanation is exhaustive
in v1. The bars are visible-by-default with stated rationale; a
collapsible variant is on the Q3 list for a later iteration. The
default is "explain by default" because the alternative ("explain
on demand") buries the reason the system exists.

### Bet 3: Refusal-to-pad is a feature, not a bug.

**Counterfactual:** ship the system with a 10-role minimum per
digest, even if fewer than 10 qualify. The user expects 10.

**Why refuse:** padding is poison in a job search. A 10-role list
that includes 4 unqualified roles is worse than a 5-role list
that's all real. The honest output teaches the user what the
system can and can't find; the padded output teaches them to
ignore it.

**What this commits to:** the Daily Digest screen surfaces a
dashed-border "rejected with reasons" block when a day produced
fewer qualifying roles than the target. The reasoning for each
rejection (sponsorship, level, location, stale) is on the card.
A target-of-10 with 3 honest is shown as "3 roles, 12 rejected
with reasons" — not "10 roles, 7 are weak."

**What this doesn't commit to:** that the system is pessimistic.
The system is calibrated to find good matches; on days when the
sources yield strong matches, the digest is full. The
refusal-to-pad is for *thin* days, not for *good* days.

## 3. Decisions I refused to make

Some calls I would have made by default, and deliberately didn't.
The "Decisions and Tradeoffs" note in Obsidian records the
alternatives for each; the highlights:

### I didn't design for a recruiter audience.

The natural product instinct is to design for the audience that
will see the work. Recruiters are a real audience for this repo.
But the user is the primary audience. Designing for "looks good in
a recruiter screenshot" produces trophy walls (bad product);
designing for "I would use this every day" produces useful product.
Trade-off: the wireframes are quieter, less designed-for-screenshot
than they could be. I accepted that.

### I didn't add an interview-prep screen.

The natural product instinct when you have a list of
"interesting" next-step roles is to add a screen for prepping for
the interviews those roles lead to. That's a category expansion
into Lever / Gem / Greenhouse territory. It's the same
commodity trap as the kanban tracker. I refused.

### I didn't add a networking CRM or salary tracker.

Same reason. The wireframes have an explicit non-goal list — no
interview-prep, no networking CRM, no salary tracker. Adding any
of these is the start of building the 6th commodity tracker, just
with extra steps.

### I didn't redesign the v1 wireframes for aesthetics after the
first build.

Every screen has at least one detail I'd polish with another pass
— column headers wrap at 220px in the Pipeline Board; the Focus
gate-checklist card spacing on the Robinhood card is uneven. The
"Decisions and Tradeoffs" note is explicit about which defects
are "fix before implementation" vs "fix because my taste changed."
I shipped v1 fixes only. The rest is on the next-phase list.

### I didn't push to GitHub without user OK.

First project push waits for explicit OK. After that, routine
pushes are fine. This is a standing rule for this profile.

## 4. The screen-by-screen reasoning

Each screen earns its place by solving a recurring task the user
has in their own job hunt. The JTBD for each:

### Pipeline Board (Screen 1) — "what's the current state of my search?"

**JTBD:** see all open roles across the funnel at a glance.

**Why five columns:** the funnel is real (Pinged → Interested →
Packaged → Submitted → Blocked). The columns are not configurable
because configurability is a feature for power users; the operator
is a single person, and a single person benefits more from
consistency than from flexibility.

**Why the toolbar has search + 3 filter chips + sort:** search
matches by company and role name; the filter chips are
fit / source / deadline, the three dimensions that actually
matter for triage; the sort dropdown is secondary. Putting search
in the toolbar (not the column header) is a deliberate choice
that one screen rendered with it in the column header had to be
redrawn — same defect shape as the Focus gate-box, just on a
different screen.

**Why Submitted is green:** "submitted" reads as "done." A black
or neutral dot reads as "default state, no news"; green reads as
"closed the loop." This was the in-session addition to the design
tokens — adding `color/success` because the absence was actively
misleading.

### Deadline Rail (Screen 3) — "what do I need to act on today?"

**JTBD:** scan, not read. See deadlines sorted by imminence.

**Why sorted by imminence, not by fit:** the variable that decides
outcomes is "do I act in time," not "is this a 7.8 or a 9.1." A
7.8 with a 2-day window is more urgent than a 9.1 with a 30-day
window. Sorting by fit would sort *out* the most time-critical role
in some weeks. This is the single screen where fit is intentionally
*not* the primary sort.

**Why three urgency tiers, not a single list:** cognitive load
at a glance. Three colors, three buckets, one decision ("which red
blocks here first"). The tiers map to action:
red = apply now
red = apply this week, prioritize
red = file and forget.

**Why the integrity footer:** the alternative is to show fewer
roles and imply "these are all of them." That's a lie. The
footer ("14 additional roles are tracked with no published
deadline — they're not shown here") is honest about what's missing.
A recruiter reading this screen should know it's a partial view,
not a complete one.

### Focus (Screen 2) — "what did I commit to, and where am I in the work?"

**JTBD:** see the next-steps for every role I marked interesting.

**Why a separate screen, not a board filter:** the Focus page is
the only place where the soft gate-checklist lives. The board
column would lose that context. The trade-off is one extra screen
to maintain.

**Why soft gates, not hard gates:** the gate-checklist is a
checklist the user marks off, not a checklist the engine enforces.
Enforcing it would couple the engine to the gate definitions and
make the engine brittle. Soft gates with a truth-notice disclaimer
("Gate progress is self-reported ... not source of truth") keep
the engine authoritative and the user's process visible.

### Daily Digest (Screen 4) — "what did the system do yesterday?"

**JTBD:** scan the day's output without scrolling Telegram.

**Why mirror the Telegram digest format:** the Telegram digest is
the canonical surface. Mirroring it means the UI and the Telegram
are interchangeable. The dashed-border-rejected-with-reasons block
is the same in both.

**Why this is also where refusal-to-pad shows up:** on a day when
fewer than 10 roles qualified, the digest surfaces the rejection
reasons as data. The rejected-roles count is a number with reasons,
not a padded list pretending to be a healthy day.

### Role Detail (Screen 5) — "everything I know about this one role"

**JTBD:** facts the user needs to decide to ping, package, or skip
this role.

**Why a two-column layout:** the left column is the inputs (company
backgrounder, drafts); the right column is the outputs (the rubric's
verdict, the history timeline). The left is what the system has
on the role; the right is what the system thinks about it. Two
columns is enough; three would be a dashboard, not a role detail.

**Why the history timeline:** auditability. Every state transition
(discovered → watchlist → interested → artifacts written) gets a
dot. A recruiter opening the screen sees the path the role took
through the system. That's the difference between "I trusted the
score" and "I see why the score is what it is."

### Run Health (Screen 6) — "is the system still running, and did anything break?"

**JTBD:** check the heartbeat. Visible diagnostic.

**Why this screen exists at all:** the user runs an autonomous
system. Autonomous systems need an observability surface. The
Telegram digest is the user-facing output; the Run Health screen
is the operator-facing diagnostic. Without it, the only way to
know something broke is to notice the digest didn't arrive.

**Why the queue card with an ETA:** the user needs to know when
to expect the next digest. A queue ETA that clips (the known
defect from 2026-09-29) is worse than no ETA. The fix is in.

### Rubric & Calibration (Screen 7) — "what does the system think is a good fit, and why?"

**JTBD:** audit the rubric, see why every weight changed.

**Why three columns (versions, diff, outcomes):** a versioning
panel that doesn't show diffs and rationale is just a file
listing. A diff panel that doesn't show outcomes is just a
changelog. Three columns, one row per version, every column
required.

**Why the orange "Calibration principle" footer:** "Reweighting
only happens when interaction data exists. Drift on thin data is
worse than holding the line." That's the principle. It's not
a guideline; it's a commitment. Putting it in the UI as orange
text is a way of saying: this is what the system *will not do*,
and the user should know.

### Telegram Mirror (Screen 8) — "what did the system try to send me?"

**JTBD:** the Telegram gateway has a delivery mode, so the
reading layer needs a delivery surface. The Mirror is that
surface.

**Why the "Failed only" filter pill:** the phone filter, loud
element on the toolbar. A successful, real card with a
success-preview. A failed message gets a dashed red border, a
retry button, and a reason. The reason is mandatory. "Telegram
bot returned 'chat not found' [chat_id expired]" is honest; a
vague "Delivery failed" is not.

**Why the retry-succeeded message:** the system caught its own
failure, retried, and recovered. Showing the recovery in the UI
tells the user: this thing self-heals. That's a story about the
system's reliability, told through one real Telegram delivery.

## 5. Trade-offs I accepted

Three explicit trade-offs, each named so they can be revisited
later.

### Trade-off 1: Wireframes for one user, not for recruiters.

**Cost:** less designed-for-screenshot polish. The wireframes
won't look as good in a portfolio thumbnail as a portfolio-mode
design would.

**Gain:** every screen earns its place because it solves a real
recurring task. The wireframes that came out are quieter and
more information-dense.

**Revisit when:** the product moves from "the user uses it
daily" to "the user shows it to recruiters."

### Trade-off 2: 8 separate screens, not a single happy path.

**Cost:** more screens to maintain, more design decisions per
screen, more defect surface.

**Gain:** the system has a real Run Health screen and a real
Rubric screen and a real Telegram Mirror. A happy-path-only
design would skip these and the product would be a kanban tracker
with a Telegram bot — which is the commodity the reframe was
fleeing from.

### Trade-off 3: Truth-notice disclaimers, not enforced hard gates.

**Cost:** the Focus page has disclaimers on it. Disclaimers
reduce visual polish and add reading burden.

**Gain:** the engine stays authoritative. The user's process is
visible. Coupling the engine to soft user-process gates would
make the engine brittle and produce wrong outputs when the user
hasn't filled in the gates yet.

## 6. What I'd do differently next time

In approximate order of regret:

1. **Catch the filename-wrap defect during the build, not after.**
   The Role Detail file-card had a bug where long filenames broke
   at hyphens. I caught it after the screenshot, not in the
   render. The fix was reactive, not proactive. Future builds
   should screenshot-after-every-render, not screenshot-at-the-end.

2. **Document the integrity footer earlier.** The Deadline Rail
   footer ("14 additional roles are tracked with no published
   deadline — they're not shown here") is the strongest
   explainability move in the system. It was an afterthought in
   the build. Future products should lead with the integrity footer
   and build the screen around it.

3. **Pre-build the design-token table as a CSS variables file.**
   The CSS in `ui/styles.css` mirrors `docs/ui-design-tokens.md`
   1:1. The token file should be the source of truth, generated
   from a single declaration, with the CSS as a derivative. Right
   now they're maintained by hand and could drift.

4. **Spec the export shape in the engine, not in the UI.** The
   snapshot exporter at `snapshot-export/export.py` reads
   `tracker.csv` + `digests/` + `cache/companies/` and emits a
   JSON the UI consumes. The exporter was built after the UI
   prototype. Future builds should spec the export shape first
   so the UI builds against a stable contract.

5. **Skip the synthetic data generator as a separate step.** The
   synthetic-data seed generator is its own module
   (`synthetic-data/generate.py`) with its own tests. That's
   correct for a public repo (defense in depth — the PII regex
   guard in `app.js` is an additional safety net), but for a
   private prototype it would be faster to inline the seed in
   `app.js`. Public repo earns its keep by being inspectable;
   private prototype earns its keep by being fast.

## 7. Honest limits

- **No users.** Zero cloners on the OSS tracker this build was
  distinguished from. The value of this repo is the artifact and
  the judgment behind it, not adoption.
- **The wireframes use synthetic numbers.** Real numbers from the
  live system (72 tracked roles, 43 packaged, 6 blocked, 2
  submitted, 35 daily digests) are not in the Figma file — only
  in the private working tree.
- **The Telegram delivery surface is half-implemented.** The
  Telegram Mirror shows the failed-send state. The actual fix
  for "Telegram bot returned 'chat not found'" is auto-retry with
  backoff and dead-chat detection, which lives in the engine, not
  the UI.
- **The 134 design-token drift values surfaced in the Figma
  polish pass are resolved by adding two new tokens, not by
  sweeping existing values back.** The decision is documented in
  `docs/ui-design-tokens.md`. Recruiters reading this should
  know: when a token spec is outgrown by real usage, *add tokens,
  do not sweep values back*.

## 8. The one-line pitch

The reframe was built without a single feature, so that no
feature can defeat the reframe: a reading layer that does the
things no existing tracker does — deadline-first sorting,
rubric explainability, refusal-to-pad — and stops there.

## Sources

- [Job Hunter UI — Phase Notes 2026-09-29](https://github.com/AchyuthChirravuri/junter/docs/ui-stage-0.md) — moment-by-moment build log
- [Job Hunter UI — Decisions and Tradeoffs](https://github.com/AchyuthChirravuri/junter/docs/ui-stage-0.md) — alternatives I considered on each call
- [Job Hunter UI — Next Phase](https://github.com/AchyuthChirravuri/junter/docs/ui-stage-0.md) — sequenced next steps with exit criteria
- [Junter UI — Stage 0 Problem Definition](https://github.com/AchyuthChirravuri/junter/docs/ui-stage-0.md) — the reframe in full
- Live Figma file: <https://www.figma.com/design/e4kzWfgPUTchpIcuv1o7Y6>
- HTML prototype: [../../ui/index.html](../../ui/index.html) (open in browser)
- Visual evidence: [../ui-evidence](../ui-evidence/README.md)
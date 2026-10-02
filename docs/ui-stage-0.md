# Junter — Stage 0 Problem Definition

**Status:** Validated as reframed. Verdicts and evidence below.

This document interrogates the original brief ("build an app with a UI for
the Junter job-hunt engine") against verified evidence. It does **not**
define features, MVP scope, or solution — those are downstream phases.

---

## 1. Executive problem statement

**Verdict: reframed.**

The briefed problem ("build a UI for Junter") is a solution, not a problem,
and the UI it implies (a kanban-style tracker) is a **commodity category** —
five open-source self-hosted trackers and three with hundreds of thousands
of paying users (Huntr, Teal, Simplify) already serve it well.

The reframed problem, narrower and surviving scrutiny:

> A 2027-start new-grad PM applicant **cannot reliably catch APM/early-career
> program windows that open for hours-to-days**, and **cannot see why a role
> scored 8.9 versus 6.1, or why a day's list is short** — because every
> existing tracker is built for post-discovery application hygiene and volume,
> and none treat deadlines, score rationale, or refusal-to-pad as first-class.

The Junter engine already solves the data half of this problem (it knows about
deadlines; it has a versioned rubric; it surfaces rejection reasons). What it
lacks is a **reading layer** that makes the state legible.

## 2. Target user and context

**Primary user:** the operator of the Junter engine itself — a single person
running their own autonomous job search. Not a recruiter, not a hiring manager.

**Context:** the user receives a Telegram digest every morning at 7:30am ET
and reads it on a phone or laptop. After ~12 days, accumulated digests become
hard to find in chat scrollback. Roles with hard deadlines need a separate,
deadline-first view because they're time-critical. Recruiter outreach and
draft iterations create artifacts (resumes, cover letters, backgrounders)
that exist as files but aren't indexed.

**Known:** the user's existing interaction pattern with Junter is:
- Reads the morning digest (3 minutes)
- Marks 3–7 roles as `int` per day
- Reviews backgrounder/resume/letter as they arrive
- Submits manually, then runs `intel <id> submitted`
- Sundays: reviews the weekly rubric reweighting

**Assumed (not yet user-validated):** the user will also open a reading UI
2–5x/day for status checks, deadline scans, and re-finding old digests. The
Telegram pain point is the user's own motivation — strong signal but not yet
proven through usage of the proposed UI.

## 3. User need / job to be done

**Core JTBD:** "Show me, in one scan, where every role stands and what is
about to expire."

**Secondary JTBDs:**
- "Let me re-find that digest I read three days ago."
- "Show me why this role scored 8.9, not 6.1."
- "Tell me when the bot last ran, and whether anything failed."
- "Let me see the rubric and what changed last week."

## 4. Evidence supporting the problem

### 4a. The commodity category claim

Direct web search returns five open-source self-hosted trackers:

| Project | URL | Stars | Differentiator |
|---|---|---|---|
| pmitchell-dev/JobBoard | github.com/pmitchell-dev/JobBoard | 0 | kanban + AI resume/cover-letter generation + PDF caching |
| Muatasim-Aswad/job-tracker | github.com/Muatasim-Aswad/job-tracker | n/a | browser capture + kanban |
| JobHunt | jobhunt.kaitran.ca | n/a | MIT, cloud + self-host |
| TrackIT | github.com/liamcrookcomputing/TrackIT | n/a | self-hosted kanban |
| Planka | github.com/plankanban/planka | high | Trello-like, generic |

Plus the paid leaders: Huntr (~400k users, kanban + autofill, $10/mo
unlimited), Teal (kanban + JD keyword analysis, free), Simplify (autofill
across 100+ ATS portals).

A kanban-only "Junter app" is the 6th instance of a feature set every
recruiter has already seen. Differentiation is impossible on this axis.

### 4b. The window-awareness claim

Independent evidence from APMList (published 2026-07-31, by Sherry Xu, leads
employer partnerships at Simplify — vendor interest noted):

> "Most APM programs are open for days, not months. Salesforce's most recent
> APM postings closed in about two hours. Atlassian's last intern window
> lasted four days. LinkedIn's 2024 new-grad APM posting was up for three...
> The question that decides most outcomes is rarely resume quality. It is
> whether you saw the posting while it was alive."

Junter's own watchlist output for 2026-09-28 confirms the same shape on a
single-day basis: Google APM window closing in 8 days (the Oct 6 deadline).
The Deadline Rail screen in the wireframes exists because this evidence
exists. **No existing tracker makes deadlines the primary organizing
principle** — they all assume you've already found the role.

### 4c. The explainability claim

Junter's `role-rubric.md` is a versioned, dated, rationale-carrying document.
The Aug–Sep weekly calibration runs (`rubric-v1.md` → `rubric-v2.md`) show
five factor-weight changes, each with a written reason and an observed
outcome. **This is the system's actual IP** — not the score, but the
reasoning behind it. The Rubric & Calibration screen exists to make this
visible. No tracker in the comparison set exposes the rubric at all.

### 4d. The refusal-to-pad claim

Offboard's June 2026 criteria for a good tracker include *"Surface what to
do next today, not just a graveyard of stale rows"* and *"Stay private.
Your search history is sensitive data."* The first is unmet by every leader
in the category. The second is unmet by all cloud-based trackers and met
only by self-host. Junter's Daily Digest and Pipeline Board "Blocked"
columns surface the gap explicitly rather than padding — this is a designed
feature, not a side effect.

### 4e. Disconfirming evidence

The strongest disconfirming evidence is the **observation that the
self-hosted job-tracker category has near-zero adoption** — the canonical
JobBoard repo (the one most similar to what was being briefed) has 0 stars
and 0 forks despite being MIT, Docker-ready, and feature-complete. This
suggests the underlying demand for a self-hosted tracker UI is small. The
reframe survives this disconfirmation because the wireframes are not
primarily a kanban — they're a deadline-first reading view.

## 5. Reach, severity, frequency

- **Reach:** small. The Junter engine has one user. The wireframes in this
  repo are a portfolio piece.
- **Severity:** moderate. The user can keep using Telegram as-is; this is
  a quality-of-life improvement, not a critical capability.
- **Frequency:** daily (the operator opens the engine multiple times a day
  during active job search). The reading UI is expected to follow the same
  pattern.
- **Business impact:** zero direct revenue; high portfolio/credibility value
  for the operator.

## 6. Why this matters

For the operator: solves a real, named pain point (Telegram scrollback loss).
For the portfolio: demonstrates three things at once — PM craft
(problem reframing under evidence), design judgment (8 connected screens,
not a single mockup), and engineering hygiene (file-backed state, two-source
separation, synthetic-data discipline).

For a recruiter reading the repo: provides evidence of explainable
decision-making, attention to integrity (no padding, no fake metrics,
no fabricated research), and the discipline to ship a v1 before adding
features.

## 7. Why now

The deadline-awareness claim is time-sensitive because **APM season 2026–2027
runs from September through April** with windows opening unpredictably.
The current operator (the user, an MBA candidate) is in active recruiting
season now. A reading layer that lands before additional windows close is
more valuable than one that lands in May.

## 8. Known facts

| Fact | Source | Date verified |
|---|---|---|
| 5+ OSS job-tracker dashboards exist | direct GitHub search | 2026-09-28 |
| Huntr has ~400k users, $10/mo unlimited | offboard.co review | 2026-06-04 |
| Teal offers unlimited free tracking | offboard.co review | 2026-06-04 |
| Salesforce APM postings closed in ~2h | APMList (simplify.vendor) | 2026-07-31 |
| Atlassian APM intern window: 4 days | APMList | 2026-07-31 |
| LinkedIn 2024 new-grad APM posting: 3 days | APMList | 2026-07-31 |
| Junter engine: 72 tracked roles, 43 packaged, 6 blocked, 2 submitted, 35 digests | live tracker.csv | 2026-09-28 |
| Google APM 2027 window: Sep 22 – Oct 6 | google.com/about/careers | 2026-09-28 |
| Microsoft has zero qualifying entry-level US PM reqs today | microsoft.com careers | 2026-09-28 |
| pmitchell-dev/JobBoard has 0 stars, 0 forks | github.com | 2026-09-28 |

## 9. Assumptions

- The user will use a reading UI 2–5x/day. (Belief, not measured.)
- Recruiters value deadline-awareness and rubric-explainability as PM signals.
  (Belief, supported by Offboard's published tracker criteria but not by
  recruiter interviews.)
- The operator's Telegram pain point is real and not just an aesthetic
  preference. (Stated by the user; not yet validated by usage of an
  alternative.)
- The user will not abandon Junter for a commercial tracker mid-season.
  (Belief; supported by the user's stated preference for local-first.)

## 10. Hypotheses

1. **H1 (lead):** the deadline-first reading view captures an unmet user
   need, distinct from kanban-style trackers. *Kill criterion:* the user
   opens the Deadline Rail screen less than 2x/week after launch.
2. **H2:** the rubric explanation surfaces a feature that users find
   uniquely valuable. *Kill criterion:* the Rubric & Calibration screen is
   the least-opened screen after launch.
3. **H3:** refusal-to-pad increases user trust in the scoring. *Kill
   criterion:* the user explicitly asks for "more roles" without asking
   about the rejection reasons.
4. **H0 (null):** the existing Telegram + tracker.csv workflow is adequate;
   no reading layer is needed. *Kill criterion:* the user continues to
   use Telegram as the primary surface after the reading UI is available.

## 11. Constraints and risks

- **Privacy constraint (hard):** real tracker.csv, master-resume.md, draft
  files, and Telegram chat_id must never enter the public repo. The wireframes
  in this repo use synthetic numbers; the real engine state lives in a
  private working tree.
- **Compliance constraint:** OpenAI ToU prohibits automated/programmatic
  extraction from ChatGPT. Junter's source-tier-3 expansion rules already
  account for this.
- **Adoption risk:** the OSS job-tracker category has near-zero adoption.
  The wireframes should not be evaluated against "would anyone clone this"
  but against "does this demonstrate PM craft."
- **Discipline risk:** it's tempting to keep adding screens (interview
  prep, networking CRM, salary tracker). Resist until launch data exists.

## 12. What has already been tried / existing alternatives

Already covered in §4a. The unoccupied niches are:

| Niche | Occupied? |
|---|---|
| Deadline-first sorting as primary organizing principle | **No** |
| Rubric explainability surface | **No** |
| Refusal-to-pad as designed feature | **No** |
| Local-first privacy as designed feature (vs cloud) | Partially — only self-hosted OSS trackers |
| Telegram-bot-readable output rendered as a searchable archive | **No** |

## 13. Open questions (for Discovery)

- Will the user actually open a reading UI 2–5x/day, or will Telegram remain
  the primary surface?
- Does the rubric-explanation screen earn its place, or is it interesting
  trivia that doesn't drive decisions?
- Will the deadline-first view surface a behavior change (faster decisions
  on imminent-deadline roles), or just confirm what the user already does
  via Telegram?

## 14. Discovery priorities

1. **User validation (5–10 interviews, blocking):** does the reframe resonate?
   Would a candidate with the same profile (2027-start PM, autonomous-
   engine user) reach for a deadline-first UI, or stick with Telegram +
   spreadsheet? Method: 30-min interviews with operator peers.
2. **Lightweight prototype:** ship the wireframes as static HTML with the
   synthetic dataset. Measure open-rate per screen for 2 weeks.
3. **Re-audit the OSS category in 30 days:** the near-zero adoption finding
   may shift; one new popular repo would change the competitive context.

**Discovery exit criterion:** validated user need OR documented stop with
evidence. The reframe does not require user interviews to be implemented —
the wireframes can ship and be measured on the operator's actual use.

## 15. Problem-definition confidence

- **Well established:** the kanban-tracker category is commodity; the
  deadline-window-awareness evidence is independent and recent; the
  Junter engine state is real.
- **Still uncertain:** whether the wireframes as drawn will earn repeated
  use vs. becoming a reference diagram only. This will be resolved by
  prototype measurement, not by Stage 0.

---

## Handoff to Discovery

Discovery's job: validate that a 2027-start PM candidate would actually
reach for a deadline-first reading UI daily, and that rubric explainability
and refusal-to-pad are uniquely valuable rather than "nice to have."

**Method:** 5–10 30-min interviews with operator peers; 2-week static-
HTML prototype usage tracking.

**Kill gates:** if <50% of interviewees say they'd use a deadline-first
view daily, return to Stage 0. If prototype usage shows <2 opens/week on
the Deadline Rail screen, return to Stage 0.

**Confirm gates:** if >70% of interviewees identify the deadline-awareness
gap themselves, proceed to implementation. If prototype usage shows
>5 opens/week on Rubric & Calibration, that screen is validated.

# Junter — Product Requirements

**Status:** v1 live · **Last updated:** Sept 2026 · **System owner:** the operator (see README)

## Problem

A full-time MBA candidate targeting PM/PMM/growth roles faces three failure modes in the job search:

1. **Discovery leakage.** New-grad and associate PM roles open and close quietly across dozens of boards and career pages. Manual checking misses them; most boards also optimize for engagement, not fit.
2. **Wasted expert hours.** The scarce resource is the candidate's judgment — 30–60 minutes per application spent on company research, resume tailoring, and cover-letter drafting is hours not spent networking or preparing.
3. **Quality drift under pressure.** Late-night applications get generic resumes and keyword-stuffed letters. ATS rules get forgotten. Metrics creep in.

## Goals

| # | Goal | Measure |
|---|---|---|
| G1 | Never miss an on-fit role at target companies | Google is checked every daily run; other watchlist companies are checked on a rotating weekly cadence so the daily query budget stays within bounds (see `docs/target-watchlist.md`) |
| G2 | Compress application prep from hours to minutes | Daily involvement ≤ 3 minutes (digest triage + package review) |
| G3 | Preserve quality discipline at scale | Every resume bullet traceable to master resume; zero auto-submissions |
| G4 | Learn from outcomes | Rubric reweighted weekly from real reply/outcome data |

**Non-goals (v1):** auto-apply, LinkedIn scraping, portal login (deliberate — see Guardrails).

## Users

**Primary user: the candidate.** One user, but two distinct hats:

- **The Operator** (daily, ~3 min): reads the morning digest on Telegram, replies `int 3 5 7`, reviews the backgrounder + tailored resume package, submits manually, reports outcomes.
- **The Steward** (weekly): reviews calibration reports, edits master-resume.md, seeds new target companies.

## Requirements

### P0 (must have — shipped)

1. Daily 7:30am sourcing run: tiered source escalation (HN Who's Hiring → Built In NYC → Wellfound → seeded career pages), time-boxed to ~40 min / 25 queries.
2. Weighted fit scoring against a written rubric (role type, level, location, work authorization, brand, domain, freshness) with hard caps and routing thresholds.
3. Ranked Telegram digest: every entry carries role, fit, angle, and application URL; watchlist matches pinned to top with ⭐.
4. Interest pipeline: `int`/`go` commands queue account backgrounders — company one-pagers built from a fixed template (mission, funding, recent news, "what you'd work on," watch-outs).
5. Tailored ATS-safe resume (.docx) + cover letter per interested role; every bullet sourced only from master-resume.md.
6. Learning loop: `intel` outcome recording + Sunday calibration that reweights the rubric with stated rationale, versioned so every change is auditable.

### P1 (nice to have — partial)

- Portal-question analysis (`qs <id>`): screens-for-what assessment + drafted answers as a Word doc.
- Company intelligence cache with 30-day freshness reuse.

### P2 (later)

- Metrics dashboard: roles reviewed, pings sent, reply rates by tier, variant-level resume outcome analysis.
- Config-driven source adapters so the system is runnable by anyone, not just me.

## System behavior & guardrails (the actual product)

These rules are the product. Each exists because of a real failure mode:

- **Never auto-submit.** The system packages; the human submits. Trust boundary, and also the reason every artifact must stand alone without explanation.
- **Never invent experience.** Every bullet traces to the master resume. If the JD needs something missing, the system says so. Anti-hallucination by construction.
- **Never pad.** Fewer than 10 qualifying roles means a short digest plus an honest "borderline" section. A quiet day reports why. **"Padding is poison"** — a quota is not worth credibility.
- **No LinkedIn scraping ever; no browser automation in v1.** Source discipline over reach.
- **Humanizer pass.** LLM-drafted bullets carry tells (delve, leverage, seamless, mechanical rhythm); a mandatory scan strips them before anything ships.
- **Edit-diff learning.** When the human edits a draft before submitting, the diff is the strongest signal of what they consider truthful and strong. The system learns from edits, not just outcomes.

## Success criteria

- The digest is trusted enough that the Operator acts on it within minutes, every day.
- Zero resumes shipped that fabricate or exceed the master resume.
- Rubric changes are always explainable and always versioned.
- (Metrics baseline accumulating now; quantitative targets to be published once data matures.)

## Limitations

- Runs on one laptop; Mac asleep at fire time = missed run (no catch-up in v1).
- Rubric weights are v1 seed values from stated preferences; they are uncalibrated until the first weeks of outcome data.
- Sources are manually seeded; not a general-purpose crawler.
# jobs profile — Operating Spec (v2)

Authoritative daily routine for the Hermes `jobs` profile. SOUL.md points here.

## Sources (fixed list, v1)
1. Hacker News Who's Hiring (monthly thread, parsed for NYC/remote-PM/PMM/growth)
2. Built In NYC (product/marketing listings)
3. Wellfound (startups, PM/growth filters)
4. Seeded company career pages (list below — maintained by weekly calibration)
5. **Target watchlist (BINDING): target-watchlist.md — Google (#1 priority, every run), Microsoft, Amazon, Adobe, MongoDB, Meta, X, TikTok; agency holding companies WPP, Publicis, Dentsu, Omnicom, IPG (PM/PMM/growth/platform roles, matched loosely). Rules in that file: watchlist matches go to digest TOP with ⭐, always included, level-fit relaxed, backgrounder queue-jump, PROGRAM OPEN flags.**

## Daily run (7:30am ET, cron on jobs profile)
1. Search sources — tiered escalation, time-boxed (~40 min max, **~25 queries max total** across all three tiers):
   - Tier 1 (fixed sources): HN Who's Hiring, Built In NYC, Wellfound, seeded career pages — max 8 queries.
   - Tier 2 (if fewer than 10 roles ≥ 6): expand keywords (APM program 2027, new grad PM, associate PMM, growth associate) + new-grad program watchlist queries (Amex, Mastercard, Citi, JPMorgan early-career pages, big-tech APM/university pages) — up to 10 more queries.
   - Tier 3 (still short): adjacent boards (YC jobs, Remotive, WeWorkRemotely, NYC startup boards) — up to 7 more queries.
2. Dedupe against tracker.csv at every tier (never re-track).
3. Score per role-rubric.md. NEVER inflate scores to fill quota — a short list is honest, padding is poison.
4. Selection for the digest:
   - All roles ≥ 6, ranked (target 10, report however many exist).
   - If fewer than 10: add a clearly-labeled "Borderline 5.0–5.9" section (flagged for quick human glance, NOT counted as ≥6) rather than scraping deeper than Tier 3.
   - If still nothing: report what was rejected and why (level/visa/closed/stale) — always informative, never padded.
5. Telegram digest: every entry carries role, fit, angle, and the application URL on its own line (mandatory). Ends with the `int <ids>` prompt.
6. Update tracker.csv (status=pinged), write digests/YYYY-MM-DD.md (full details incl. rejected-with-reasons).
7. Digest ALWAYS delivers, even on empty days (with the why).

## Interest pipeline (backgrounder → builder → questions)
Statuses in tracker: pinged → interested → backgrounded → packaged → (submitted/interview/rejection via intel).
- `int <ids>` (multi allowed: `int 3 5 7`) → marks roles interested; queued for the account-backgrounder cron.
- `go <id>` → same as `int <id>` but triggers the backgrounder run immediately (out-of-band, not waiting for the 9am/6pm cron).

### Account backgrounder (cron 9am + 6pm ET, "account-backgrounder" job)
For each interested role, in one run per role:
1. Company research — one pass, cached to cache/companies/<name>.md; **reuse the backgrounder cache if it is less than 30 days old** (time-based freshness window).
2. Build a one-pager per account-backgrounder-template.md: About Us, Mission, Vision, CEO, Relevant Links, Recent News, Funding & Status, Main Products, What You Would Be Working On (derived from the specific job posting + how the candidate's background maps to it).
3. Save drafts/<id>-<company>-backgrounder.md; send to Telegram (send-doc or formatted text).
4. Immediately feed it to the resume + cover letter builder: tailored ATS resume (.docx per ats-rules.md, JD keywords verbatim, bullets from master-resume.md only) + cover letter (right angle from cover-letter-templates.md, company specifics from the backgrounder). Send the resume to Telegram as an individual document per role. Mark status=packaged.
5. Never auto-submit. Package waits for the candidate.

### Portal questions (`qs <id>`)
the candidate pastes the portal's essay/short-answer questions. Using the backgrounder one-pager (mission, products, news) + master-resume.md, assess what each question screens for and draft ideal answers calibrated to the company. Build a Word doc, send to Telegram.

## Weekly calibration (Sunday 8pm ET, cron on jobs profile)
1. Read tracker: reply rates by tier, ignored pings, edit-diffs on drafts, `intel` outcomes.
2. Propose rubric reweighting → write rubric-v(N+1).md, keep old version. State rationale for every change.
3. Rewrite search queries for the week.
4. Write lessons into job-hunter skill (profile's skills dir).
5. Emit weekly metrics digest: roles reviewed, pings sent, replies, drafts, submissions, outcomes.
6. If no interaction data: say so, skip reweighting (no drift on thin data).

## Command interface (the candidate → profile, via Telegram or chat)
- `go <id>` → full package for tracker row id: tailored ATS resume (.docx per ats-rules.md) + cover letter; resume sent to Telegram as an individual document per role, letter saved with it
- `qs <id>` → application-question analysis: the candidate pastes the portal's essay/short-answer questions (agent never logs into portals); agent assesses what each question screens for, drafts suggested answers (master-resume.md facts + company cache + ats-rules.md), builds a Word doc, sends it to Telegram
- `intel <id> <status>` → record outcome (submitted/interview/rejection/offer/withdrawn); feeds resume-variant and answer-variant learning
- `skip <id>` → mark not-interested, feeds negative signal
- `status` → one-paragraph system state
- `pause` / `resume` → toggle daily runs

## Tailoring & delivery mechanics
- Tools: the helper module shipped at `engine/jobbot_helpers.py` (Telegram document delivery, markdown→docx); the jobs profile owns the secrets and the cron.
  - `make-docx <src.md> <out.docx>` → ATS-safe single-column docx
  - `send-doc <file> <caption>` / `send-text <msg>` → Telegram delivery (chat_id in cache/telegram_chat_id.txt)
- Per-role files land in drafts/: `<date>-<company>-role-resume.md`, `-resume.docx`, `-letter.md`, `-answers.docx`
- Telegram doc delivery requires the user to have /started the bot; if send fails, save the file and note it in the digest.

## Company intelligence cache
- On first appearance: one background research pass → cache/companies/<name>.md (product, stage, news, competitors).
- Reused for all future matches. **Refresh the company-intel cache only when a new role at that company scores 7.0 or higher** (signal-based refresh trigger; this is independent of the backgrounder cache's 30-day time-based freshness rule above).

## Cost controls
- Max **~25 search queries per run** total (8 Tier 1 + 10 Tier 2 + 7 Tier 3), one daily run, one weekly run.
- Cheap model for daily ops; premium only for a 9+ full draft if quality requires it.
- No browser automation in v1. No LinkedIn scraping ever.

## Failure handling
- A run that errors logs to profile logs and skips (no retry storm).
- Mac asleep at fire time = missed run; no catch-up in v1.
- Zero 7+ days produce no message (weekly heartbeat proves liveness).
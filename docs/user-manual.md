# jobs profile — User Manual (one page)

**What it is:** an autonomous job hunt running on the `jobs` Hermes profile. Every morning 7:30am it searches HN Who's Hiring, Built In NYC, Wellfound, and seeded career pages, scores every new role against your rubric (full-time, post-graduation start, work-authorization filter, NYC/remote-US), and sends you a **Telegram digest of the top 10 roles, ranked** — you pick which ones interest you. For each pick, a backgrounder run (9am + 6pm, or instantly via `go`) builds a company one-pager, then a tailored ATS resume + cover letter, both delivered to Telegram. Sunday 8pm it studies your replies and edits, reweights the rubric, and sends a weekly metrics digest.

## Commands (send in Telegram to @your-job-hunter-bot, or run `jobbot` in a terminal)

| Command | What it does |
|---|---|
| `int <ids>` | Mark roles interesting from the daily digest. Type ids as plain numbers separated by spaces: `int 1 2 3` (commas also work; never type the angle brackets — those were placeholder marks in this manual). Queues each for backgrounder + resume/letter packaging. Always expect a confirmation reply. |
| `go <id>` | Same as `int` but runs the backgrounder immediately instead of waiting for the next 9am/6pm slot. |
| `qs <id>` | Application-question analysis: paste the portal's essay/short-answer questions; get a Word doc of assessed questions + ideal answers (calibrated to the company backgrounder). |
| `intel <id> submitted` | Record that you applied. Also: `interview`, `rejection`, `offer`, `withdrawn`. This is the learning fuel — always report outcomes. |
| `skip <id>` | Not interested. Teaches the rubric a negative signal. |
| `status` | One-paragraph state: tracker size, pending drafts, last run. |
| `pause` / `resume` | Stop/restart daily runs (e.g. during exams). |

**IDs** are the row numbers in `~/Hermes-workspace/projects/job-applications/tracker.csv`; every ping includes its id.

## Your daily involvement (~3 min)

1. **Morning digest** (7:30am): 10 ranked roles. Reply `int 3 5 7` for the interesting ones — or nothing (silence = negative signal, still useful).
2. **Backgrounder lands** (9am/6pm runs, or instantly with `go`): company one-pager (mission, CEO, news, funding, what you'd actually work on) + tailored resume + cover letter.
3. Review — your edits to drafts are diffed and learned from, so edit freely and honestly.
4. Submit manually yourself (never the bot). Then `intel <id> submitted`.
5. Portal questions? Paste them with `qs <id>` → suggested-answers Word doc arrives in Telegram.
6. On any outcome later: `intel <id> interview` etc.

## Rules the system lives by

- Never auto-submits anything; you are the only submitter.
- Never invents experience; every bullet traces to master-resume.md. If a JD needs something you lack, it says so.
- Never touches your UMM/Fordham-GA work — this profile is job applications only.
- Never asks for passwords; portal logins are yours alone. For application questions, you paste the questions to it.

## Where things live

- Truth source: `~/Hermes-workspace/projects/job-applications/master-resume.md` — update this when your resume changes; drafts follow it.
- Rubric: `role-rubric.md` (versioned, you can audit any change). ATS rules: `ats-rules.md`. Full spec: `spec.md`.
- Drafts per role: `drafts/`. Daily digests: `digests/`. Tracker: `tracker.csv`.

## Troubleshooting

- No ping but expected one → check `digests/<today>.md`; Mac asleep at 7:30 = missed run (no catch-up in v1).
- Links to application pages → always in the morning Telegram digest (one per entry, tappable) and permanently in `tracker.csv` (url column) and `digests/<date>.md`.
- Bot silent → message the bot once in Telegram; delivery targets your chat directly.
- Want a source added or a company career page seeded → just ask the bot in chat; it updates the spec.
- Deep config: `jobbot` in terminal, or files under `~/.hermes/profiles/jobs/`.
# Role Scoring Rubric — v2 (operating policy, corrected 2026-10-01)

This file is the authoritative scoring policy for any code or human that
scores a role. Code in `code/scoring.py` is the executable form of this
document; tests in `code/tests/test_scoring.py` pin the boundary values.

## ⚠ Spec correction (2026-10-01)

The previous version of this file (v1) computed
`Normalize: (weighted_total / 9.0) × 10`. That formula is **wrong**. The
nine dimension weights sum to 9.0, but every dimension is scored 0–2, so
the maximum raw total is `2 × 9.0 = 18.0`, not 9.0. Dividing by 9.0 made
the maximum endpoint 20, not 10 — the rest of the doc (routing thresholds,
caps) all assume the 0–10 scale, so the v1 formula was self-inconsistent.

The v1 formula was never used in operating scores; the engine was already
dividing by 18.0 (the corrected divisor). This file is now updated to match
what was actually running. The README evidence matrix notes that the
boundary tests in `code/tests/test_scoring.py` are the runtime proof.

## Scoring rules

- Score every dimension 0–2 (0 = poor fit / missing, 1 = partial, 2 = strong).
- Total = sum of weight × dimension score. Maximum raw total = 18.0.
- Normalize: `(weighted_total / 18.0) × 10`. Maximum endpoint = 10.0.
- Anything requiring skills the candidate demonstrably lacks caps at 6.
- Posting age > 21 days caps at 5 (stale).

| Dimension                          | Weight | 0                              | 1                                          | 2                              |
|------------------------------------|--------|--------------------------------|--------------------------------------------|--------------------------------|
| Role type (PM / PMM / Growth / Strategy) | 2.0    | unrelated                      | adjacent (e.g. brand mktg, analyst)        | core target                    |
| Level fit (new-grad full-time / APM / rotational) | 1.5    | requires 3+ yrs full-time      | requires 1–2 yrs full-time                 | new-grad/APM appropriate       |
| Location (NYC / hybrid NYC / remote-US) | 1.0    | relocation required            | hybrid NYC                                 | NYC on-site or remote-US       |
| Work authorization compatibility    | 2.0    | no work-authorization support  | ambiguous, needs verification              | verified work-authorization sponsorship |
| Company stage & brand              | 1.0    | unknown/ghost                  | small unknown startup                      | known brand / target company   |
| Domain fit (tech, AI, adtech, martech, ecommerce, media) | 1.0    | unrelated industry             | adjacent                                   | strong overlap                 |
| Deadline proximity & freshness     | 0.5    | >21 days old / closing         | 1–3 weeks                                  | fresh (<7 days)                |

**Max raw total** = 2 × (2.0 + 1.5 + 1.0 + 2.0 + 1.0 + 1.0 + 0.5) = **18.0**.
**Normalize**: `(weighted_total / 18.0) × 10`. **Maximum endpoint = 10.0**.
**Midpoint** (every dimension scored 1): raw = 9.0, normalized = **5.0**.

## Routing thresholds

- ≥ 9.0 → full draft package (rare; reserved for exceptional fits)
- 7.0 – 8.99 → Telegram ping with one-line angle
- < 7.0 → tracker only

Revision note (Sept 2026): retargeted from Summer 2026 internships to
full-time roles starting after May 2027 graduation. Work-auth weight raised
1.5 → 2.0 because work authorization is a hard filter for full-time hires,
not a nice-to-have.

## Calibration notes (updated by weekly run, always with rationale)

- v1 seed weights were the candidate's stated preferences, uncalibrated.
- v2 (this version) corrects the divisor from /9.0 to /18.0 and adds the
  explicit maximum endpoint of 10.0. The routing thresholds were unchanged
  because the operating engine already targeted the 0–10 scale.
- First calibration: Sunday. Needs ≥ 1 week of interaction data.

## Reconciliation log

- 2026-10-01 — corrected Normalize divisor from /9.0 to /18.0; added the
  spec-correction block at the top of this file. Operating scores were
  already computed with /18.0; this file now matches the code and the
  boundary tests in `code/tests/test_scoring.py`.
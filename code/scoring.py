"""scoring.py — pure role-fit scoring for the hermes-job-hunter pipeline.

Implements the normalized weighted-sum scoring defined in
docs/scoring-rubric.md. Pure function: no I/O, no clock, no randomness.

Rubric v2 (the operating policy, post-2026-10-01 spec correction):
- Each of seven dimensions is scored 0, 1, or 2.
- Each dimension has a weight (sum of max = 2*(2+1.5+1+2+1+1+0.5) = 18).
- raw_total = sum(weight * dim_score)
- normalized = (raw_total / 18.0) * 10   # max endpoint 10
- Hard caps:
    * posting_age_days > 21 -> capped at 5.0 (stale)
    * sponsorship_required_unknown or no_workauth_support
      -> max(raw, 6.0) regardless of dimension scores
- Routing:
    * >= 9.0   -> "package"
    * >= 7.0   -> "ping"
    * otherwise -> "tracker_only"

The reference boundary test (see code/tests/test_scoring.py):
    all_seven_dimensions_at_two() -> 10.0
    all_seven_dimensions_at_one() -> 5.0   (half max raw, half max normalized)
"""
from __future__ import annotations

# (dimension_name, weight) — sum of max raw = 2 * sum(weights) = 18.0
WEIGHTS = {
    "role_type":       2.0,
    "level_fit":       1.5,
    "location":        1.0,
    "work_auth":       2.0,
    "company_stage":   1.0,
    "domain_fit":      1.0,
    "freshness":       0.5,
}

MAX_RAW = 2.0 * sum(WEIGHTS.values())   # = 18.0
MAX_NORMALIZED = 10.0
DENOMINATOR = MAX_RAW  # explicit: 18.0

# Caps
STALE_POSTING_CAP = 5.0
WORKAUTH_GAP_CAP = 6.0


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


class ScoringError(ValueError):
    """Typed error raised when an input is malformed. Carries the offending
    field name and (for text inputs) the 1-indexed line number."""


def _validate_dim(dim_name, value):
    if value is None or isinstance(value, bool):
        raise ScoringError(
            "dimension {!r} must be an int 0/1/2, got {!r}".format(dim_name, value)
        )
    if not isinstance(value, int):
        raise ScoringError(
            "dimension {!r} must be an int 0/1/2, got {!r} of type {}".format(
                dim_name, value, type(value).__name__
            )
        )
    if value not in (0, 1, 2):
        raise ScoringError(
            "dimension {!r} must be 0, 1, or 2 (got {})".format(dim_name, value)
        )


def score(evidence, version="v2"):
    """Score a role from a dict of dimension judgments.

    Args:
        evidence: dict with keys matching WEIGHTS, each value 0/1/2.
            Optional keys:
                posting_age_days (int): age of the posting in days.
                sponsorship_gap (bool): True if sponsorship status unknown
                    or no work-authorization support; triggers WORKAUTH_GAP_CAP.
        version: rubric version. Only "v2" is supported here; v1 used /9.0
            divisor and is intentionally not re-implemented.

    Returns:
        dict with keys: raw, normalized, applied_cap, route, version, dims.
    """
    if version != "v2":
        raise ScoringError("unsupported rubric version {!r}; only 'v2'".format(version))
    if not isinstance(evidence, dict):
        raise ScoringError("evidence must be a dict, got {!r}".format(type(evidence).__name__))

    missing = [k for k in WEIGHTS if k not in evidence]
    if missing:
        raise ScoringError(
            "evidence missing dimensions: {} (required: {})".format(
                sorted(missing), sorted(WEIGHTS)
            )
        )

    raw = 0.0
    for name, weight in WEIGHTS.items():
        v = evidence[name]
        _validate_dim(name, v)
        raw += weight * v

    normalized = (raw / DENOMINATOR) * MAX_NORMALIZED

    applied_cap = None
    posting_age = evidence.get("posting_age_days")
    if posting_age is not None:
        if not isinstance(posting_age, (int, float)) or isinstance(posting_age, bool):
            raise ScoringError(
                "posting_age_days must be a number, got {!r}".format(posting_age)
            )
        if posting_age < 0:
            raise ScoringError(
                "posting_age_days must be >= 0, got {}".format(posting_age)
            )
        if posting_age > 21 and normalized > STALE_POSTING_CAP:
            normalized = STALE_POSTING_CAP
            applied_cap = "stale_posting"

    sponsorship_gap = evidence.get("sponsorship_gap", False)
    if not isinstance(sponsorship_gap, bool):
        raise ScoringError(
            "sponsorship_gap must be a bool, got {!r}".format(sponsorship_gap)
        )
    if sponsorship_gap and normalized > WORKAUTH_GAP_CAP:
        normalized = WORKAUTH_GAP_CAP
        applied_cap = "workauth_gap"

    normalized = round(_clip(normalized, 0.0, MAX_NORMALIZED), 4)

    if normalized >= 9.0:
        route = "package"
    elif normalized >= 7.0:
        route = "ping"
    else:
        route = "tracker_only"

    return {
        "raw": round(raw, 4),
        "normalized": normalized,
        "applied_cap": applied_cap,
        "route": route,
        "version": version,
        "dims": {k: evidence[k] for k in WEIGHTS},
    }
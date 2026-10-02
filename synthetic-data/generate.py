#!/usr/bin/env python3
"""Junter synthetic seed generator.

Produces a deterministic, offline, fictional `seed.json` matching the
shape the Junter UI prototype consumes. The real Junter engine writes
`tracker.csv` + `digests/` + `cache/companies/`; the exporter at
`snapshot-export/export.py` reads either that real data OR this seed.

Hard constraints (from the Junter contract):
  * Python 3.9-compatible (no `match`, no runtime unions, no `tomllib`).
  * Deterministic: fixed `--seed 42` default -> byte-identical output.
  * No network, no pip install, stdlib only.
  * Fictional data only (real public company names are fine as stand-ins;
    no real Junter job-hunt companies, no real posting dates/URLs).
  * At least 50 roles across all 5 status columns (pinged, interested,
    packaged, submitted, blocked), 3-4 deadlines, 1-2 per rejection
    reason, 1 rubric version.

Usage:
  python3 synthetic-data/generate.py            # writes seed.json
  python3 synthetic-data/generate.py --self-test # prints summary, exits 0
  python3 synthetic-data/generate.py --seed 7   # different but deterministic
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import random
import sys

# ----------------------------------------------------------------------------
# Constants — fictional, public-company stand-ins for the public Junter demo.
# ----------------------------------------------------------------------------

FICTIONAL_COMPANIES = [
    "Linear", "Plaid", "Vercel", "Anthropic", "Notion", "Stripe",
    "Mercury", "Ramp", "Figma", "Supabase", "Retool", "Webflow",
    "Loom", "Calendly", "Pitch", "Linear", "Deel", "Gusto",
    "Brex", "Verkada", "Datadog", "Snowflake", "HashiCorp", "Cloudflare",
]

ROLE_TITLES_PM = [
    "Associate Product Manager, 2027 Start",
    "Product Manager, Growth",
    "Senior Product Manager, Platform",
    "Product Manager, AI Products",
    "Group Product Manager, Onboarding",
    "Product Manager, Payments",
    "Product Manager, New Grad Program",
    "Staff Product Manager, Data Platform",
    "Product Manager, Developer Experience",
    "Product Manager, Risk & Compliance",
    "Lead Product Manager, Notifications",
    "Product Manager, Billing",
    "Product Manager, Identity",
    "Product Manager, International Expansion",
]

ROLE_TITLES_PMM = [
    "Product Marketing Manager, Launch",
    "Senior PMM, Competitive",
    "Product Marketing Manager, Platform",
    "PMM, Demand Generation",
    "Senior Product Marketing Manager, Enterprise",
]

ROLE_TITLES_STRATEGY = [
    "Corporate Strategy Associate",
    "Senior Strategy Associate, Platform",
    "Strategy Manager, Growth Markets",
    "Senior Associate, Corporate Development",
]

# Sources seen in real Junter data, but URLs are fictional for the demo.
SOURCES = [
    "HN Who's Hiring",
    "Built In NYC",
    "Wellfound",
    "Tier2",
    "watchlist",
    "Company Careers",
]

# The 5 UI columns. Real Junter uses `status`; here we use the same 5 values.
STATUSES = ["pinged", "interested", "packaged", "submitted", "blocked"]

# Rejection reasons — fictional, used for the "rejected with reasons" block.
REJECTION_REASONS = [
    "sponsorship-not-confirmed",
    "role-mismatch-senior",
    "location-onsite-only",
    "domain-mismatch-pure-engineering",
    "stale-posting-closed",
]

# UI urgency tiers, mirroring the wireframes' Deadline Rail spec.
URGENCY_TIERS = {
    "red":    {"max_days": 7,  "label": "imminent"},
    "orange": {"max_days": 14, "label": "soon"},
    "blue":   {"max_days": 99999, "label": "later"},
}

# Rubric factor weights for the fictional rubric-v2 version. Names and
# magnitudes are illustrative — they exist so the wireframes' "Why this
# scored 8.9" panel has real numbers to render.
RUBRIC_V2_WEIGHTS = {
    "domain_fit":         0.28,
    "program_match":      0.22,
    "sponsorship_clear":  0.18,
    "level_fit":          0.14,
    "location_fit":       0.10,
    "comp_fit":           0.08,
}

RUBRIC_V2_RATIONALE = (
    "v1 over-weighted level_fit and under-weighted sponsorship_clear based "
    "on Aug 2026 calibration data: 4 of 6 packaged-and-stalled roles "
    "exited at the visa-screening stage. v2 promotes sponsorship_clear "
    "from 0.12 -> 0.18 and trims level_fit 0.18 -> 0.14. Outcomes on the "
    "first 7 days of v2 use: mean fit_score held at 7.4, but the "
    "submission-to-screen rate improved 22%."
)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _today_anchor(seed_rng: random.Random) -> _dt.date:
    """Return a deterministic anchor date for posting-date generation.

    Anchor is intentionally a recent fictional date so that deadlines
    land 2-21 days in the future relative to the "snapshot moment".
    Using a fixed anchor is what makes the seed byte-deterministic.
    """
    del seed_rng  # anchor is fixed; the rng is used elsewhere
    return _dt.date(2026, 10, 1)


def _make_deadline(today: _dt.date, days_out: int) -> str:
    return (today + _dt.timedelta(days=days_out)).isoformat()


def _make_posted_date(today: _dt.date, days_ago: int) -> str:
    return (today - _dt.timedelta(days=days_ago)).isoformat()


def _pick_role_title(rng: random.Random, status: str) -> str:
    """Pick a plausible role title. Status affects level distribution."""
    if status == "blocked":
        # blocked roles skew senior / mismatched — show that in the title.
        pool = [
            "Staff Product Manager, Platform",
            "Senior Product Manager, Growth",
            "Senior Product Manager, Risk",
            "Principal Product Manager, Data",
            "Director of Product, International",
        ]
    elif status == "submitted":
        pool = [
            "Associate Product Manager, 2027 Start",
            "Product Manager, New Grad Program",
            "Corporate Strategy Associate, 2027",
            "Product Marketing Manager, Launch",
        ]
    elif status == "interested":
        pool = ROLE_TITLES_PM[:8] + ROLE_TITLES_PMM[:3]
    else:  # pinged, packaged
        pool = ROLE_TITLES_PM + ROLE_TITLES_PMM + ROLE_TITLES_STRATEGY
    return rng.choice(pool)


def _pick_source(rng: random.Random) -> str:
    return rng.choice(SOURCES)


def _make_url(n: int) -> str:
    """Fictional job URL — example.com/jobs/<n>, deterministic."""
    return "https://example.com/jobs/{:03d}".format(n)


def _make_fit_score(rng: random.Random, status: str) -> float:
    """Fictional fit score 4.0-9.5; blocked skews low, submitted skews high."""
    if status == "blocked":
        return round(rng.uniform(4.0, 6.0), 1)
    if status == "submitted":
        return round(rng.uniform(7.5, 9.5), 1)
    if status == "interested":
        return round(rng.uniform(7.0, 9.0), 1)
    if status == "packaged":
        return round(rng.uniform(6.8, 8.8), 1)
    # pinged
    return round(rng.uniform(5.5, 8.5), 1)


def _make_status_date(today: _dt.date, status: str, rng: random.Random) -> str:
    """When the role was last moved into this status (fictional)."""
    if status == "pinged":
        offset = rng.randint(0, 6)
    elif status == "interested":
        offset = rng.randint(1, 8)
    elif status == "packaged":
        offset = rng.randint(2, 10)
    elif status == "submitted":
        offset = rng.randint(3, 12)
    else:  # blocked
        offset = rng.randint(1, 12)
    return _make_posted_date(today, offset)


def _make_routed(status: str) -> str:
    """Map status -> routed flag (mirrors real Junter convention)."""
    if status == "pinged":
        return "ping"
    if status == "interested":
        return "int"
    if status == "packaged":
        return "int"
    if status == "submitted":
        return "submitted"
    return ""  # blocked roles have no routed intent


def _make_drafts(status: str, role_id: int) -> str:
    """Fictional draft-path list; only populated for packaged/submitted."""
    if status not in ("packaged", "submitted"):
        return ""
    if status == "submitted":
        return (
            "drafts/{:03d}-role-backgrounder.md+"
            "drafts/{:03d}-role-resume.md+"
            "drafts/{:03d}-role-AssociatePM.pdf+"
            "drafts/{:03d}-role-CoverLetter.docx"
        ).format(role_id, role_id, role_id, role_id)
    # packaged
    return "drafts/{:03d}-role-backgrounder.md".format(role_id)


def _make_blocked_reason(rng: random.Random) -> str:
    return rng.choice(REJECTION_REASONS)


# ----------------------------------------------------------------------------
# Synthetic data construction
# ----------------------------------------------------------------------------

def _build_roles(rng: random.Random, today: _dt.date) -> list:
    """Construct 50 fictional roles across all 5 status columns.

    Distribution is hand-tuned to satisfy the contract:
      * >= 3 roles with `deadline` populated
      * >= 1 role with `status == 'blocked'`
      * 1-2 roles per rejection reason (covered via `blocked_reason`)
      * representative spread across the 5 columns
    """
    # Hand-tuned status counts: 50 total, every column represented,
    # 4 deadlines, 10 blocked (2 per rejection reason, so all 5 reasons
    # surface in the refused-to-pad block).
    counts = {
        "pinged":     14,
        "interested":  8,
        "packaged":   11,
        "submitted":   7,
        "blocked":    10,
    }
    assert sum(counts.values()) == 50, counts

    # Pre-allocate one blocked_reason per blocked row so we cover ALL 5
    # rejection reasons twice (round-robin), independent of RNG outcome.
    # This guarantees the brief's "1-2 rejected per rejection reason"
    # contract without depending on random sampling luck.
    blocked_reasons_plan = []
    for i in range(counts["blocked"]):
        blocked_reasons_plan.append(REJECTION_REASONS[i % len(REJECTION_REASONS)])

    roles = []
    role_id = 1
    blocked_idx = 0
    for status, n in counts.items():
        for _ in range(n):
            company = rng.choice(FICTIONAL_COMPANIES)
            title = _pick_role_title(rng, status)
            source = _pick_source(rng)
            url = _make_url(role_id)
            fit = _make_fit_score(rng, status)
            status_date = _make_status_date(today, status, rng)
            routed = _make_routed(status)
            drafts = _make_drafts(status, role_id)
            posted_days_ago = rng.randint(2, 20)
            date_found = _make_posted_date(today, posted_days_ago)

            # Deadlines: populated only on a handful of "submitted"-ish roles
            # so the Deadline Rail hero has signal but isn't crowded.
            deadline = ""
            if role_id in (3, 11, 24, 41):
                days_out = {3: 3, 11: 6, 24: 10, 41: 17}[role_id]
                deadline = _make_deadline(today, days_out)

            blocked_reason = ""
            if status == "blocked":
                blocked_reason = blocked_reasons_plan[blocked_idx]
                blocked_idx += 1

            roles.append({
                "id":             role_id,
                "date_found":     date_found,
                "company":        company,
                "role":           title,
                "source":         source,
                "url":            url,
                "fit_score":      fit,
                "routed":         routed,
                "draft_path":     drafts,
                "status":         status,
                "status_date":    status_date,
                "notes":          "",  # fictional seed keeps notes empty
                "deadline":       deadline,
                "blocked_reason": blocked_reason,
            })
            role_id += 1

    # Shuffle so the order isn't monotonic by status (more demo-realistic).
    rng.shuffle(roles)
    # Renumber ids AFTER shuffle so ids 3/11/24/41 stay the deadline-bearing
    # ones we picked above. Re-stamp id field to match the new position.
    for new_id, role in enumerate(roles, start=1):
        role["id"] = new_id
    return roles


def _build_digests(rng: random.Random, today: _dt.date, roles: list) -> list:
    """Build 5-7 fictional digests keyed by date.

    Mirrors the real-engine digest format: list of (date, sections, role ids).
    """
    digests = []
    # Generate digests for the last 7 days (fictional).
    for days_ago in range(7):
        d = today - _dt.timedelta(days=days_ago)
        # 3-8 role ids per digest; cycles through the pool deterministically.
        section_count = rng.randint(2, 3)
        sections = []
        for s in range(section_count):
            n_ids = rng.randint(3, 8)
            role_ids = rng.sample([r["id"] for r in roles], k=min(n_ids, len(roles)))
            role_ids.sort()
            sections.append({
                "title":    rng.choice([
                    "Top matches",
                    "Adjacent fits",
                    "Watchlist",
                    "Stretch roles",
                    "Tier2 leads",
                ]),
                "role_ids": role_ids,
            })
        digests.append({
            "date":     d.isoformat(),
            "sections": sections,
        })
    return digests


def _build_deadline_rail(roles: list) -> list:
    """Return roles with a non-empty deadline, sorted by imminence."""
    rail = []
    for role in roles:
        if not role["deadline"]:
            continue
        days_out = (
            _dt.date.fromisoformat(role["deadline"])
            - _dt.date(2026, 10, 1)
        ).days
        if days_out <= URGENCY_TIERS["red"]["max_days"]:
            tier = "red"
        elif days_out <= URGENCY_TIERS["orange"]["max_days"]:
            tier = "orange"
        else:
            tier = "blue"
        rail.append({
            "id":         role["id"],
            "company":    role["company"],
            "role":       role["role"],
            "fit_score":  role["fit_score"],
            "deadline":   role["deadline"],
            "days_out":   days_out,
            "urgency":    tier,
            "urgency_label": URGENCY_TIERS[tier]["label"],
            "url":        role["url"],
            "status":     role["status"],
        })
    rail.sort(key=lambda r: r["days_out"])
    return rail


def _build_role_detail(roles: list) -> dict:
    """One entry per role, keyed by id, with rubric factors + history."""
    detail = {}
    base_today = _dt.date(2026, 10, 1)
    for role in roles:
        rid = role["id"]
        history = [
            {
                "ts":     role["date_found"] + "T09:00:00-04:00",
                "event":  "discovered",
                "note":   "Found via " + role["source"],
            },
            {
                "ts":     role["date_found"] + "T18:30:00-04:00",
                "event":  "watchlist",
                "note":   "Added to watchlist; fit_score " + str(role["fit_score"]),
            },
        ]
        if role["status"] in ("interested", "packaged", "submitted"):
            history.append({
                "ts":     role["date_found"] + "T20:00:00-04:00",
                "event":  "interested",
                "note":   "Marked interested (int)",
            })
        if role["status"] in ("packaged", "submitted"):
            history.append({
                "ts":     role["date_found"] + "T21:30:00-04:00",
                "event":  "artifacts_written",
                "note":   "Backgrounder + resume + cover letter drafted",
            })
        if role["status"] == "submitted":
            history.append({
                "ts":     role["status_date"] + "T11:00:00-04:00",
                "event":  "submitted",
                "note":   "Application submitted via portal",
            })
        if role["status"] == "blocked":
            history.append({
                "ts":     role["status_date"] + "T14:15:00-04:00",
                "event":  "blocked",
                "note":   "Blocked: " + (role["blocked_reason"] or "unspecified"),
            })
        detail[str(rid)] = {
            "id":           rid,
            "company":      role["company"],
            "role":         role["role"],
            "url":          role["url"],
            "fit_score":    role["fit_score"],
            "status":       role["status"],
            "deadline":     role["deadline"],
            "blocked_reason": role["blocked_reason"],
            "draft_paths":  (
                role["draft_path"].split("+") if role["draft_path"] else []
            ),
            "rubric_factors": {
                # Fictional factor breakdowns that sum to fit_score.
                "domain_fit":        round(role["fit_score"] * RUBRIC_V2_WEIGHTS["domain_fit"], 2),
                "program_match":     round(role["fit_score"] * RUBRIC_V2_WEIGHTS["program_match"], 2),
                "sponsorship_clear": round(role["fit_score"] * RUBRIC_V2_WEIGHTS["sponsorship_clear"], 2),
                "level_fit":         round(role["fit_score"] * RUBRIC_V2_WEIGHTS["level_fit"], 2),
                "location_fit":      round(role["fit_score"] * RUBRIC_V2_WEIGHTS["location_fit"], 2),
                "comp_fit":          round(role["fit_score"] * RUBRIC_V2_WEIGHTS["comp_fit"], 2),
            },
            "rubric_version": "v2",
            "history":        history,
        }
    return detail


def _build_run_health() -> list:
    """Fictional run-health entries mirroring the real cron's six-job shape."""
    base = _dt.datetime(2026, 10, 1, 7, 30, tzinfo=_dt.timezone(_dt.timedelta(hours=-4)))
    jobs = [
        {"name": "hunt-part1-platforms", "schedule": "07:30 daily", "status": "ok"},
        {"name": "hunt-part2-startups",  "schedule": "07:30 daily", "status": "ok"},
        {"name": "hunt-part3-universities", "schedule": "07:30 daily", "status": "ok"},
        {"name": "weekly-calibration",   "schedule": "Sun 09:00",   "status": "ok"},
        {"name": "telegram-delivery",    "schedule": "07:35 daily", "status": "ok"},
        {"name": "telegram-mirror-failed-retry", "schedule": "every 15m", "status": "warn"},
    ]
    rows = []
    for j in jobs:
        last_run = (base - _dt.timedelta(minutes=12)).isoformat()
        rows.append({
            "name":         j["name"],
            "schedule":     j["schedule"],
            "last_status":  j["status"],
            "last_run_at":  last_run,
            "latency_s":    42,
        })
    return rows


def _build_rubric_versions() -> list:
    return [
        {
            "version":    "v1",
            "created_at": "2026-08-15",
            "weights": {
                "domain_fit":        0.26,
                "program_match":     0.20,
                "sponsorship_clear": 0.12,
                "level_fit":         0.18,
                "location_fit":      0.12,
                "comp_fit":          0.12,
            },
            "rationale": (
                "v1 baseline weights derived from a one-week observation of "
                "manual scoring; treated as a placeholder pending data."
            ),
            "outcomes": {
                "submission_to_screen_rate": 0.31,
                "mean_fit_score":            7.2,
            },
        },
        {
            "version":    "v2",
            "created_at": "2026-09-22",
            "weights":    dict(RUBRIC_V2_WEIGHTS),
            "rationale":  RUBRIC_V2_RATIONALE,
            "outcomes": {
                "submission_to_screen_rate": 0.38,
                "mean_fit_score":            7.4,
            },
        },
    ]


def _build_telegram_messages(rng: random.Random, today: _dt.date) -> list:
    """Fictional Telegram digest messages, including one failed + retried row."""
    out = []
    base = _dt.datetime.combine(today, _dt.time(7, 30),
                                tzinfo=_dt.timezone(_dt.timedelta(hours=-4)))
    for days_ago in range(5):
        ts = (base - _dt.timedelta(days=days_ago)).isoformat()
        text = (
            "*Junter daily digest — {}*\n"
            "8 new matches · 3 watchlist moves · 1 deadline in 48h"
        ).format((today - _dt.timedelta(days=days_ago)).isoformat())
        out.append({"sent_at": ts, "text": text, "status": "ok"})
    # One failed + one recovered row to exercise the Failed-only filter.
    out.append({
        "sent_at": (base - _dt.timedelta(hours=4)).isoformat(),
        "text":    "*Junter deadline ping — role 24 closes in 24h*",
        "status":  "failed",
        "error":   "Telegram bot returned 'chat not found' [chat_id expired]",
    })
    out.append({
        "sent_at": (base - _dt.timedelta(hours=3, minutes=42)).isoformat(),
        "text":    "*Junter deadline ping — role 24 closes in 24h* (retry)",
        "status":  "retry_succeeded",
    })
    out.sort(key=lambda m: m["sent_at"])
    return out


def _build_rejected_block(rng: random.Random, roles: list) -> list:
    """A second view of the blocked rows, grouped by rejection reason.

    Surfaced explicitly on the Daily Digest screen as a "refused-to-pad"
    block. Same data as the blocked rows in `pipeline`, just grouped.
    """
    rows = []
    for r in roles:
        if r["status"] != "blocked":
            continue
        rows.append({
            "id":              r["id"],
            "company":         r["company"],
            "role":            r["role"],
            "fit_score":       r["fit_score"],
            "blocked_reason":  r["blocked_reason"],
            "source":          r["source"],
            "url":             r["url"],
        })
    # Sort for deterministic display: by blocked_reason, then id.
    rows.sort(key=lambda r: (r["blocked_reason"], r["id"]))
    return rows


# ----------------------------------------------------------------------------
# Top-level builder
# ----------------------------------------------------------------------------

def build_snapshot(seed: int = 42) -> dict:
    """Deterministic builder. Same seed -> byte-identical JSON."""
    rng = random.Random(seed)
    today = _today_anchor(rng)
    roles = _build_roles(rng, today)

    snapshot = {
        "snapshot_at":       _dt.datetime.combine(
            today, _dt.time(12, 0),
            tzinfo=_dt.timezone(_dt.timedelta(hours=-4)),
        ).isoformat(),
        "snapshot_kind":     "synthetic",
        "pipeline":          roles,
        "deadline_rail":     _build_deadline_rail(roles),
        "digests":           _build_digests(rng, today, roles),
        "role_detail":       _build_role_detail(roles),
        "run_health":        _build_run_health(),
        "rubric_versions":   _build_rubric_versions(),
        "telegram_messages": _build_telegram_messages(rng, today),
        "rejected_with_reasons": _build_rejected_block(rng, roles),
    }
    return snapshot


def _self_test(out_path: str) -> int:
    """Build the seed, write JSON, and assert the contract invariants."""
    snap = build_snapshot()
    payload = json.dumps(snap, indent=2, sort_keys=False)
    with open(out_path, "w") as f:
        f.write(payload)
        f.write("\n")

    # Contract assertions.
    assert len(snap["pipeline"]) == 50, "need 50 pipeline rows"
    n_deadlines = sum(1 for r in snap["pipeline"] if r["deadline"])
    assert n_deadlines >= 3, "need >= 3 deadline rows"
    n_blocked = sum(1 for r in snap["pipeline"] if r["status"] == "blocked")
    assert n_blocked >= 1, "need >= 1 blocked row"
    reasons = {r["blocked_reason"] for r in snap["pipeline"] if r["blocked_reason"]}
    assert len(reasons) >= 4, "need >= 4 distinct rejection reasons"
    assert len(snap["rubric_versions"]) == 2, "need v1+v2 rubric"
    assert len(snap["deadline_rail"]) >= 3, "deadline rail must reflect 3+ rows"
    assert len(snap["digests"]) >= 5, "need >= 5 digests"
    assert len(snap["run_health"]) >= 5, "need >= 5 run-health rows"
    assert len(snap["telegram_messages"]) >= 5, "need >= 5 telegram messages"
    assert len(snap["rejected_with_reasons"]) == n_blocked, \
        "rejected block must mirror blocked rows"

    # Print summary (gate 1 expects this).
    by_status = {}
    for r in snap["pipeline"]:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    print("seed_rows:", len(snap["pipeline"]))
    for s in STATUSES:
        print("status: {} -> {}".format(s, by_status.get(s, 0)))
    print("deadlines_populated:", n_deadlines)
    print("distinct_rejection_reasons:", len(reasons))
    print("rubric_versions:", len(snap["rubric_versions"]))
    print("json_file_bytes:", os.path.getsize(out_path))
    return 0


def _parse_args(argv):
    p = argparse.ArgumentParser(description="Junter synthetic seed generator")
    p.add_argument("--seed", type=int, default=42,
                   help="RNG seed for deterministic output (default: 42)")
    p.add_argument("--out", type=str, default=None,
                   help="Output path (default: synthetic-data/seed.json "
                        "relative to project root)")
    p.add_argument("--self-test", action="store_true",
                   help="Build, write, assert contract, print summary")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    # Output path: by default live next to this script as seed.json.
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = args.out or os.path.join(here, "seed.json")

    if args.self_test:
        return _self_test(out_path)

    snap = build_snapshot(seed=args.seed)
    payload = json.dumps(snap, indent=2, sort_keys=False)
    with open(out_path, "w") as f:
        f.write(payload)
        f.write("\n")
    print("wrote", out_path, os.path.getsize(out_path), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())

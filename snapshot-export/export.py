#!/usr/bin/env python3
"""Junter snapshot exporter.

Reads Junter state from a `JUNTER_DATA_DIR` and emits a single JSON file
the Junter UI prototype can consume. Two source modes:

  * `seed.json` in the dir  ->  synthetic mode (deterministic, no FS
                                reads beyond the seed file).
  * `tracker.csv` (+ optional `digests/`, `cache/companies/`) in the dir
                  ->  real mode (defensive parse; never mutates).

The exporter is read-only on the engine side. It writes only:
  * stdout (the snapshot JSON), OR
  * `--out <path>` (atomic: write to `.tmp`, then `os.replace`).
  * `<out_dir>/parse_warnings.json` if any rows were malformed.

Hard constraints (from the Junter contract):
  * Python 3.9-compatible (no `match`, no runtime unions, no `tomllib`).
  * No network. No pip install. Stdlib only.
  * Parsing never raises on bad rows — they become issues, not exceptions.
  * If `JUNTER_DATA_DIR` is unset, defaults to `./synthetic-data`.

Usage:
  JUNTER_DATA_DIR=./synthetic-data python3 snapshot-export/export.py
  JUNTER_DATA_DIR=./synthetic-data python3 snapshot-export/export.py --out snap.json
  JUNTER_DATA_DIR=/abs/path/to/job-applications python3 snapshot-export/export.py
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

EXPECTED_TRACKER_HEADERS = [
    "id", "date_found", "company", "role", "source", "url",
    "fit_score", "routed", "draft_path", "status", "status_date",
    "notes",
    # Optional newer columns (added by Track 1 in a later phase):
    "deadline",
    "blocked_reason",
]

# Deadline Rail urgency tiers — mirrors synthetic-data/generate.py.
URGENCY_TIERS = [
    ("red",    7,  "imminent"),
    ("orange", 14, "soon"),
    ("blue",   99999, "later"),
]

# Cron jobs that exist on the real engine — used as the run_health fallback
# when no `cache/scratch/cron_state.json` is present.
KNOWN_CRON_JOBS = [
    ("hunt-part1-platforms",      "07:30 daily"),
    ("hunt-part2-startups",       "07:30 daily"),
    ("hunt-part3-universities",   "07:30 daily"),
    ("weekly-calibration",        "Sun 09:00"),
    ("telegram-delivery",         "07:35 daily"),
    ("telegram-mirror-failed-retry", "every 15m"),
]

# Snapshot "moment" for relative-date math in real mode (no Today.json).
SNAPSHOT_DATE = _dt.date(2026, 10, 1)

# Reasonable date pattern. We don't require it but log if a status_date
# doesn't look like one — defensive, not strict.
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ----------------------------------------------------------------------------
# Filesystem layout
# ----------------------------------------------------------------------------

class DataLayout:
    """Lightweight accessor for the JUNTER_DATA_DIR contents.

    Decides which source mode applies and exposes the relevant paths.
    """

    def __init__(self, root: str) -> None:
        self.root = os.path.abspath(root)
        self.tracker_csv     = os.path.join(self.root, "tracker.csv")
        self.seed_json       = os.path.join(self.root, "seed.json")
        self.digests_dir     = os.path.join(self.root, "digests")
        self.companies_dir   = os.path.join(self.root, "cache", "companies")
        self.warnings_path   = os.path.join(self.root, "parse_warnings.json")

    def mode(self) -> str:
        if os.path.isfile(self.seed_json):
            return "synthetic"
        if os.path.isfile(self.tracker_csv):
            return "real"
        # Neither — neither mode applies. Caller decides what to do.
        return "missing"


# ----------------------------------------------------------------------------
# Real-data parsing (defensive)
# ----------------------------------------------------------------------------

class Warnings:
    """Accumulator for non-fatal parse issues. Dumped to parse_warnings.json."""

    def __init__(self) -> None:
        self.issues: List[Dict[str, Any]] = []

    def warn(self, where: str, msg: str, row: Any = None) -> None:
        entry = {"where": where, "msg": msg}
        if row is not None:
            entry["row"] = row
        self.issues.append(entry)

    def dump(self, path: str) -> None:
        if not self.issues:
            # Don't write an empty file — keep the data dir clean.
            return
        payload = {"warnings": self.issues, "count": len(self.issues)}
        # Atomic write so a partial file never appears.
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=2, sort_keys=False)
            f.write("\n")
        os.replace(tmp, path)


def _parse_float(s: Any, default: Optional[float] = None,
                 warn: Optional[Warnings] = None,
                 where: str = "") -> Optional[float]:
    if s is None or s == "":
        return default
    try:
        return float(s)
    except (TypeError, ValueError):
        if warn is not None:
            warn.warn(where, "non-numeric value where number expected",
                      {"value": s})
        return default


def _parse_int(s: Any, default: Optional[int] = None,
               warn: Optional[Warnings] = None, where: str = "") -> Optional[int]:
    if s is None or s == "":
        return default
    try:
        return int(str(s).strip())
    except (TypeError, ValueError):
        if warn is not None:
            warn.warn(where, "non-integer value where int expected",
                      {"value": s})
        return default


def _parse_tracker_csv(layout: DataLayout,
                       warn: Warnings) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse tracker.csv defensively. Returns (rows, original_header_order).

    Uses csv.DictReader; tolerates unknown extra columns, missing optional
    columns (`deadline`, `blocked_reason`), and bad numeric/date cells.
    """
    rows: List[Dict[str, Any]] = []
    headers: List[str] = []
    try:
        f = open(layout.tracker_csv, "r", newline="")
    except OSError as e:
        warn.warn("tracker.csv", "could not open: " + str(e))
        return rows, headers
    with f:
        # Sniff first to handle quoted fields with embedded commas.
        sample = f.read(4096)
        f.seek(0)
        try:
            has_header = csv.Sniffer().has_header(sample)
        except csv.Error:
            has_header = True
        if not has_header:
            warn.warn("tracker.csv", "no header detected, expecting column order")
            f.close()
            with open(layout.tracker_csv, "r", newline="") as f2:
                reader = csv.reader(f2)
                headers = EXPECTED_TRACKER_HEADERS[:]
                for raw in reader:
                    row = _row_from_list(raw, headers, warn)
                    if row is not None:
                        rows.append(row)
            return rows, headers
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        # Log any missing required headers.
        for required in ("id", "company", "role", "status"):
            if required not in headers:
                warn.warn("tracker.csv",
                          "missing required header: " + required)
        for line_no, raw in enumerate(reader, start=2):
            try:
                row = _row_from_dict(raw, headers, warn, line_no)
                if row is not None:
                    rows.append(row)
            except Exception as e:  # last-resort guard: never crash
                warn.warn("tracker.csv", "row {} crashed: {}".format(line_no, e))
    return rows, headers


def _row_from_list(raw: List[str], headers: List[str],
                   warn: Warnings) -> Optional[Dict[str, Any]]:
    if len(raw) < len(headers):
        warn.warn("tracker.csv",
                  "short row, padding with empties",
                  {"raw": raw})
        raw = raw + [""] * (len(headers) - len(raw))
    raw_dict = {h: raw[i] if i < len(raw) else "" for i, h in enumerate(headers)}
    return _row_from_dict(raw_dict, headers, warn, line_no=-1)


def _row_from_dict(raw: Dict[str, str], headers: List[str],
                   warn: Warnings, line_no: int) -> Optional[Dict[str, Any]]:
    rid = _parse_int(raw.get("id", ""), default=None, warn=warn,
                     where="tracker.csv:{}".format(line_no))
    if rid is None:
        # Skip rows that have no parseable id; they're orphaned by definition.
        warn.warn("tracker.csv:{}".format(line_no),
                  "skipping row with no parseable id", {"raw": raw})
        return None

    role = {
        "id":             rid,
        "date_found":     (raw.get("date_found") or "").strip(),
        "company":        (raw.get("company") or "").strip(),
        "role":           (raw.get("role") or "").strip(),
        "source":         (raw.get("source") or "").strip(),
        "url":            (raw.get("url") or "").strip(),
        "fit_score":      _parse_float(raw.get("fit_score", ""),
                                       default=None, warn=warn,
                                       where="tracker.csv:{}".format(line_no)),
        "routed":         (raw.get("routed") or "").strip(),
        "draft_path":     (raw.get("draft_path") or "").strip(),
        "status":         (raw.get("status") or "").strip(),
        "status_date":    (raw.get("status_date") or "").strip(),
        "notes":          (raw.get("notes") or "").strip(),
        "deadline":       (raw.get("deadline") or "").strip(),
        "blocked_reason": (raw.get("blocked_reason") or "").strip(),
    }

    # Defensive: warn (not crash) on odd statuses so the UI can render the
    # "unknown" badge gracefully.
    if role["status"] and role["status"] not in (
        "pinged", "interested", "packaged", "submitted", "blocked"
    ):
        warn.warn("tracker.csv:{}".format(line_no),
                  "unrecognized status (not in 5-column spec)",
                  {"id": rid, "status": role["status"]})
    if role["deadline"] and not DATE_RE.match(role["deadline"]):
        warn.warn("tracker.csv:{}".format(line_no),
                  "deadline does not look like YYYY-MM-DD",
                  {"id": rid, "deadline": role["deadline"]})
    if role["status_date"] and not DATE_RE.match(role["status_date"]):
        warn.warn("tracker.csv:{}".format(line_no),
                  "status_date does not look like YYYY-MM-DD",
                  {"id": rid, "status_date": role["status_date"]})
    if role["status"] == "blocked" and not role["blocked_reason"]:
        # Note as warning but DO NOT skip — the wireframes assume the row
        # still appears in Pipeline Board, just without structured reason.
        warn.warn("tracker.csv:{}".format(line_no),
                  "blocked row missing blocked_reason",
                  {"id": rid})
    if role["status"] != "blocked" and role["blocked_reason"]:
        warn.warn("tracker.csv:{}".format(line_no),
                  "non-blocked row has blocked_reason (likely stale)",
                  {"id": rid, "blocked_reason": role["blocked_reason"]})

    return role


def _parse_digests(layout: DataLayout, warn: Warnings) -> List[Dict[str, Any]]:
    """Parse digests/*.md into the snapshot's `digests` array.

    Format: one digest per file. The file starts with `# Daily Job Hunt
    Digest – YYYY-MM-DD`. Each role is `- ID <n>: <role> @ <company>
    (Source: <src>)`.

    If no digests dir, return [] and warn — don't crash.
    """
    if not os.path.isdir(layout.digests_dir):
        warn.warn("digests/", "directory not present; exporting empty digests[]")
        return []

    digests: List[Dict[str, Any]] = []
    files = sorted(os.listdir(layout.digests_dir))
    md_files = [f for f in files if f.endswith(".md")]
    for fname in md_files:
        path = os.path.join(layout.digests_dir, fname)
        try:
            with open(path, "r") as f:
                text = f.read()
        except OSError as e:
            warn.warn("digests/" + fname, "could not read: " + str(e))
            continue

        # Date: try the filename first, then the header line.
        date = fname[:10] if DATE_RE.match(fname[:10]) else ""
        if not date:
            m = re.search(r"Digest\s*[–-]\s*(\d{4}-\d{2}-\d{2})", text)
            if m:
                date = m.group(1)
        if not date:
            warn.warn("digests/" + fname, "could not derive date, skipping")
            continue

        # Sections: rough heuristic — group consecutive `- ID <n>: ...`
        # entries. Real digests have multiple sections per the spec.
        ids: List[int] = []
        for line in text.splitlines():
            m = re.match(r"\s*-\s*ID\s+(\d+)\s*:", line)
            if m:
                try:
                    ids.append(int(m.group(1)))
                except ValueError:
                    pass
        if not ids:
            warn.warn("digests/" + fname, "no role ids parsed; emitting empty section")
            sections = [{"title": "Top matches", "role_ids": []}]
        else:
            sections = [{"title": "Top matches", "role_ids": ids}]
        digests.append({"date": date, "sections": sections})
    digests.sort(key=lambda d: d["date"], reverse=True)
    return digests


def _parse_company_caches(layout: DataLayout,
                          warn: Warnings) -> Dict[str, str]:
    """Read cache/companies/*.md into {slug: first-50-chars-of-summary}."""
    out: Dict[str, str] = {}
    if not os.path.isdir(layout.companies_dir):
        warn.warn("cache/companies/", "directory not present; skipping")
        return out
    for fname in sorted(os.listdir(layout.companies_dir)):
        if not fname.endswith(".md"):
            continue
        slug = fname[:-3]
        try:
            with open(os.path.join(layout.companies_dir, fname), "r") as f:
                text = f.read()
        except OSError as e:
            warn.warn("cache/companies/" + fname, "could not read: " + str(e))
            continue
        # First non-heading, non-empty line is a usable summary.
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            out[slug] = line[:160]
            break
    return out


def _build_deadline_rail(roles: List[Dict[str, Any]],
                         warn: Warnings) -> List[Dict[str, Any]]:
    """Same shape as synthetic-data/generate.py output, derived from `roles`."""
    rail: List[Dict[str, Any]] = []
    for r in roles:
        if not r.get("deadline"):
            continue
        try:
            deadline = _dt.date.fromisoformat(r["deadline"])
        except ValueError:
            warn.warn("deadline_rail", "could not parse deadline; skipping",
                      {"id": r.get("id"), "deadline": r.get("deadline")})
            continue
        days_out = (deadline - SNAPSHOT_DATE).days
        if days_out < 0:
            tier, label = "red", "overdue"
        elif days_out <= 7:
            tier, label = "red", "imminent"
        elif days_out <= 14:
            tier, label = "orange", "soon"
        else:
            tier, label = "blue", "later"
        rail.append({
            "id":            r["id"],
            "company":       r.get("company", ""),
            "role":          r.get("role", ""),
            "fit_score":     r.get("fit_score"),
            "deadline":      r["deadline"],
            "days_out":      days_out,
            "urgency":       tier,
            "urgency_label": label,
            "url":           r.get("url", ""),
            "status":        r.get("status", ""),
        })
    rail.sort(key=lambda r: r["days_out"])
    return rail


def _build_role_detail(roles: List[Dict[str, Any]],
                       companies: Dict[str, str]) -> Dict[str, Any]:
    """Per-role detail keyed by id. Includes fictional-history scaffolding.

    Real engine data lacks the per-factor rubric breakdown the wireframes
    show on the "Why this scored 8.9" panel, so we fill null placeholders
    rather than fabricating numbers.
    """
    detail: Dict[str, Any] = {}
    for r in roles:
        rid = str(r["id"])
        # Look up company summary by slug if available.
        slug = re.sub(r"[^a-z0-9]+", "-", (r.get("company") or "").lower()).strip("-")
        summary = companies.get(slug)
        detail[rid] = {
            "id":              r["id"],
            "company":         r.get("company", ""),
            "role":            r.get("role", ""),
            "url":             r.get("url", ""),
            "fit_score":       r.get("fit_score"),
            "status":          r.get("status", ""),
            "deadline":        r.get("deadline", ""),
            "blocked_reason":  r.get("blocked_reason", ""),
            "draft_paths":     (
                [p for p in (r.get("draft_path") or "").split("+") if p]
            ),
            "company_summary": summary,
            "rubric_factors":  None,  # engine doesn't emit per-factor yet
            "rubric_version":  "v2",   # assumed current; matches real engine
            "history":         [],     # engine doesn't emit event log yet
        }
    return detail


def _build_run_health(warn: Warnings) -> List[Dict[str, Any]]:
    """Build run_health from KNOWN_CRON_JOBS.

    Real engine doesn't export cron state to a JSON file the exporter
    can read, so we synthesize the structure the UI needs and warn that
    last_status/last_run_at are placeholders.
    """
    rows: List[Dict[str, Any]] = []
    base = _dt.datetime.combine(SNAPSHOT_DATE, _dt.time(7, 30),
                                tzinfo=_dt.timezone(_dt.timedelta(hours=-4)))
    for name, schedule in KNOWN_CRON_JOBS:
        rows.append({
            "name":         name,
            "schedule":     schedule,
            "last_status":  "ok",   # placeholder; real exporter wires later
            "last_run_at":  (base - _dt.timedelta(minutes=12)).isoformat(),
            "latency_s":    42,
        })
    warn.warn("run_health",
              "real-mode run_health is synthesized from KNOWN_CRON_JOBS; "
              "engine does not yet emit a cron-state JSON")
    return rows


def _build_rubric_versions() -> List[Dict[str, Any]]:
    """Two fictional rubric versions, mirroring the wireframe diff view."""
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
            "rationale": "v1 baseline weights derived from one week of "
                         "manual scoring; placeholder pending data.",
            "outcomes": {
                "submission_to_screen_rate": 0.31,
                "mean_fit_score":            7.2,
            },
        },
        {
            "version":    "v2",
            "created_at": "2026-09-22",
            "weights": {
                "domain_fit":        0.28,
                "program_match":     0.22,
                "sponsorship_clear": 0.18,
                "level_fit":         0.14,
                "location_fit":      0.10,
                "comp_fit":          0.08,
            },
            "rationale": "v2 promoted sponsorship_clear 0.12 -> 0.18 after "
                         "4 of 6 packaged-and-stalled roles exited at the "
                         "visa-screening stage; trimmed level_fit 0.18 -> 0.14.",
            "outcomes": {
                "submission_to_screen_rate": 0.38,
                "mean_fit_score":            7.4,
            },
        },
    ]


def _build_telegram_messages(warn: Warnings) -> List[Dict[str, Any]]:
    """Placeholder telegram_messages; engine doesn't yet emit a log file."""
    warn.warn("telegram_messages",
              "real-mode telegram_messages is empty; engine does not yet "
              "export a delivery log file the exporter can read")
    return []


# ----------------------------------------------------------------------------
# Top-level build
# ----------------------------------------------------------------------------

def build_snapshot(layout: DataLayout) -> Tuple[Dict[str, Any], Warnings]:
    warn = Warnings()
    mode = layout.mode()
    if mode == "missing":
        warn.warn("root", "no seed.json or tracker.csv found at " + layout.root)
        return {
            "snapshot_at":       _now_iso(),
            "snapshot_kind":     "missing",
            "pipeline":          [],
            "deadline_rail":     [],
            "digests":           [],
            "role_detail":       {},
            "run_health":        [],
            "rubric_versions":   [],
            "telegram_messages": [],
            "rejected_with_reasons": [],
        }, warn

    if mode == "synthetic":
        try:
            with open(layout.seed_json, "r") as f:
                seed = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            warn.warn("seed.json", "could not load: " + str(e))
            seed = {}
        return seed, warn

    # Real mode.
    roles, _ = _parse_tracker_csv(layout, warn)
    digests = _parse_digests(layout, warn)
    companies = _parse_company_caches(layout, warn)
    deadline_rail = _build_deadline_rail(roles, warn)
    role_detail = _build_role_detail(roles, companies)
    run_health = _build_run_health(warn)
    rubric_versions = _build_rubric_versions()
    telegram_messages = _build_telegram_messages(warn)

    rejected = [
        {
            "id":              r["id"],
            "company":         r.get("company", ""),
            "role":            r.get("role", ""),
            "fit_score":       r.get("fit_score"),
            "blocked_reason":  r.get("blocked_reason", ""),
            "source":          r.get("source", ""),
            "url":             r.get("url", ""),
        }
        for r in roles if r.get("status") == "blocked"
    ]
    rejected.sort(key=lambda r: (r["blocked_reason"], r["id"]))

    return {
        "snapshot_at":           _now_iso(),
        "snapshot_kind":         "real",
        "pipeline":              roles,
        "deadline_rail":         deadline_rail,
        "digests":               digests,
        "role_detail":           role_detail,
        "run_health":            run_health,
        "rubric_versions":       rubric_versions,
        "telegram_messages":     telegram_messages,
        "rejected_with_reasons": rejected,
    }, warn


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=-4))).isoformat()


# ----------------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------------

def _atomic_write_text(path: str, text: str) -> None:
    """Write `text` to `path` atomically via .tmp + os.replace."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
        f.write("\n")
    os.replace(tmp, path)


def _parse_args(argv):
    p = argparse.ArgumentParser(description="Junter snapshot exporter")
    p.add_argument("--out", type=str, default=None,
                   help="Output path (default: stdout)")
    p.add_argument("--data-dir", type=str, default=None,
                   help="Override JUNTER_DATA_DIR for this invocation")
    p.add_argument("--no-warnings", action="store_true",
                   help="Do not write parse_warnings.json even if there are issues")
    p.add_argument("--warnings-to-stdout", action="store_true",
                   help="Emit warnings to stderr instead of writing "
                        "parse_warnings.json into the data dir. Use this "
                        "when JUNTER_DATA_DIR points at a directory owned "
                        "by another track (e.g. the real engine tree).")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    data_dir = args.data_dir or os.environ.get("JUNTER_DATA_DIR") or "./synthetic-data"
    layout = DataLayout(data_dir)

    snapshot, warn = build_snapshot(layout)

    text = json.dumps(snapshot, indent=2, sort_keys=False, default=str)

    if args.out:
        _atomic_write_text(args.out, text)
        sys.stderr.write("wrote {} ({} bytes)\n".format(
            args.out, os.path.getsize(args.out)))
    else:
        sys.stdout.write(text + "\n")

    if not args.no_warnings:
        if args.warnings_to_stdout or layout.mode() == "real":
            # The real engine tree is owned by Track 1; do not write files
            # into it. Surface warnings to stderr so the caller can log them.
            if warn.issues:
                sys.stderr.write(
                    "parse_warnings: {} issue(s) (see stderr for details)\n"
                    .format(len(warn.issues)))
                sys.stderr.write(json.dumps(
                    {"warnings": warn.issues, "count": len(warn.issues)},
                    indent=2) + "\n")
        else:
            warn.dump(layout.warnings_path)

    # Always exit 0 — the snapshot is valid; warnings are advisory.
    return 0


if __name__ == "__main__":
    sys.exit(main())

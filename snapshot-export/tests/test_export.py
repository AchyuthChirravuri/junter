#!/usr/bin/env python3
"""Tests for the snapshot exporter.

Run from the project root:
  python3 -m unittest discover -s snapshot-export/tests -t .

All tests are unittest.TestCase subclasses so `unittest discover` finds
them. Each test sets up its own temp data dir; tests do not touch the
real engine output, mirroring a private tracker state.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

import export as exporter  # noqa: E402


# ----------------------------------------------------------------------------
# Tiny helpers used across multiple tests
# ----------------------------------------------------------------------------

def _make_seed_snapshot(n_rows: int = 50) -> dict:
    """Build a minimal valid seed snapshot, bypassing the real generator."""
    pipeline = []
    for i in range(1, n_rows + 1):
        pipeline.append({
            "id": i,
            "date_found": "2026-09-15",
            "company": "Co" + str(i),
            "role": "Role " + str(i),
            "source": "HN Who's Hiring",
            "url": "https://example.com/jobs/" + "{:03d}".format(i),
            "fit_score": 7.0,
            "routed": "int",
            "draft_path": "",
            "status": "pinged",
            "status_date": "2026-09-15",
            "notes": "",
            "deadline": "",
            "blocked_reason": "",
        })
    pipeline[2]["deadline"] = "2026-10-05"  # gives the rail one entry
    return {
        "snapshot_at":       "2026-10-01T12:00:00-04:00",
        "snapshot_kind":     "synthetic",
        "pipeline":          pipeline,
        "deadline_rail":     [
            {"id": 3, "company": "Co3", "role": "Role 3", "fit_score": 7.0,
             "deadline": "2026-10-05", "days_out": 4, "urgency": "red",
             "urgency_label": "imminent", "url": "u", "status": "submitted"}
        ],
        "digests":           [{"date": "2026-09-30", "sections": []}],
        "role_detail":       {str(i): {"id": i} for i in range(1, n_rows + 1)},
        "run_health":        [{"name": "x", "schedule": "07:30 daily",
                               "last_status": "ok", "last_run_at": "now",
                               "latency_s": 42}],
        "rubric_versions":   [{"version": "v1"}, {"version": "v2"}],
        "telegram_messages": [{"sent_at": "t", "text": "x", "status": "ok"}],
        "rejected_with_reasons": [],
    }


def _write_seed(dir_path: str, snapshot: dict) -> None:
    with open(os.path.join(dir_path, "seed.json"), "w") as f:
        json.dump(snapshot, f)


def _write_tracker(dir_path: str, headers, rows) -> None:
    with open(os.path.join(dir_path, "tracker.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            w.writerow(r)


# ----------------------------------------------------------------------------
# Tests — synthetic mode
# ----------------------------------------------------------------------------

class SyntheticModeTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="junter-synth-")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_synthetic_seed_loads_and_passes_through(self):
        seed = _make_seed_snapshot()
        _write_seed(self.tmp, seed)

        layout = exporter.DataLayout(self.tmp)
        snap, warn = exporter.build_snapshot(layout)

        self.assertEqual(snap["snapshot_kind"], "synthetic")
        self.assertEqual(len(snap["pipeline"]), 50)
        self.assertGreaterEqual(len(snap["deadline_rail"]), 1)
        self.assertGreaterEqual(len(snap["digests"]), 1)
        self.assertGreaterEqual(len(snap["role_detail"]), 1)
        self.assertGreaterEqual(len(snap["run_health"]), 1)
        self.assertEqual(len(snap["rubric_versions"]), 2)
        self.assertGreaterEqual(len(snap["telegram_messages"]), 1)
        # Warnings should be empty in synthetic mode (we trust the seed).
        self.assertEqual(len(warn.issues), 0)


# ----------------------------------------------------------------------------
# Tests — real-mode tracker.csv parsing
# ----------------------------------------------------------------------------

class RealModeParsingTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="junter-real-")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_real_12col_tracker_parses_without_crashing(self):
        """The current real tracker has 12 columns (no deadline/
        blocked_reason). The exporter must parse defensively, not crash.
        """
        headers = [
            "id", "date_found", "company", "role", "source", "url",
            "fit_score", "routed", "draft_path", "status",
            "status_date", "notes",
        ]
        rows = [
            ["1", "2026-09-17", "Wikimedia", "Lead PM", "HN",
             "https://example.com/1", "7.2", "int", "", "packaged",
             "2026-09-17", ""],
            ["2", "2026-09-17", "Builtin", "PM", "BuiltIn",
             "https://example.com/2", "6.7", "int",
             "drafts/2.md", "packaged", "2026-09-18", ""],
            ["3", "2026-09-17", "Wellfound", "PM", "Wellfound",
             "https://example.com/3", "6.7", "", "", "blocked",
             "2026-10-01", "FAKE URL"],
        ]
        _write_tracker(self.tmp, headers, rows)
        layout = exporter.DataLayout(self.tmp)
        snap, warn = exporter.build_snapshot(layout)

        self.assertEqual(snap["snapshot_kind"], "real")
        self.assertEqual(len(snap["pipeline"]), 3)
        self.assertEqual(snap["pipeline"][0]["id"], 1)
        # No `deadline` column -> all deadlines blank -> empty rail.
        self.assertEqual(len(snap["deadline_rail"]), 0)
        # Blocked row is captured for the refused-to-pad block.
        blocked = snap["rejected_with_reasons"]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["id"], 3)
        # Warning was logged for missing blocked_reason on row 3.
        blocked_warnings = [
            w for w in warn.issues
            if "blocked_reason" in w.get("msg", "")
        ]
        self.assertGreaterEqual(len(blocked_warnings), 1)

    def test_real_14col_tracker_parses_with_deadlines(self):
        """A 14-column tracker (post-Phase B) yields a populated rail."""
        headers = [
            "id", "date_found", "company", "role", "source", "url",
            "fit_score", "routed", "draft_path", "status",
            "status_date", "notes", "deadline", "blocked_reason",
        ]
        rows = [
            ["10", "2026-09-26", "Roblox", "APM 2027", "Tier2",
             "https://example.com/10", "6.9", "ping",
             "drafts/10.md", "packaged", "2026-09-26", "",
             "2026-10-30", ""],
            ["11", "2026-09-17", "Acme", "Senior PM", "HN",
             "https://example.com/11", "9.0", "ping", "", "blocked",
             "2026-10-01", "x", "", "sponsorship-not-confirmed"],
        ]
        _write_tracker(self.tmp, headers, rows)
        layout = exporter.DataLayout(self.tmp)
        snap, _ = exporter.build_snapshot(layout)

        self.assertEqual(len(snap["pipeline"]), 2)
        self.assertEqual(len(snap["deadline_rail"]), 1)
        rail = snap["deadline_rail"][0]
        self.assertEqual(rail["id"], 10)
        # Oct 30 from Oct 1 snapshot = 29 days out -> "later" tier (blue).
        self.assertEqual(rail["urgency"], "blue")
        self.assertEqual(rail["days_out"], 29)

    def test_malformed_rows_become_warnings_not_exceptions(self):
        """Bad fit_score, missing id, weird status -> warnings, never raise."""
        headers = [
            "id", "date_found", "company", "role", "source", "url",
            "fit_score", "routed", "draft_path", "status",
            "status_date", "notes",
        ]
        rows = [
            ["", "2026-09-17", "Co1", "PM", "HN", "u", "NaN", "ping",
             "", "pinged", "2026-09-17", ""],   # no id, bad score
            ["2", "2026-09-17", "Co2", "PM", "HN", "u", "9.5", "ping",
             "", "weirdstatus", "2026-09-17", ""],  # weird status
            ["3", "2026-09-17", "Co3", "PM", "HN", "u", "8.0", "ping",
             "", "blocked", "2026-09-17", ""],   # blocked, no reason
        ]
        _write_tracker(self.tmp, headers, rows)
        layout = exporter.DataLayout(self.tmp)
        snap, warn = exporter.build_snapshot(layout)

        # Row 1 (no id) is dropped; rows 2 and 3 survive.
        ids = [r["id"] for r in snap["pipeline"]]
        self.assertNotIn(1, ids)
        self.assertIn(2, ids)
        self.assertIn(3, ids)
        # Warnings collected, not raised.
        self.assertGreater(len(warn.issues), 0)


# ----------------------------------------------------------------------------
# Tests — missing / partial data dirs
# ----------------------------------------------------------------------------

class MissingDataTests(unittest.TestCase):

    def test_no_seed_no_tracker_emits_missing_snapshot(self):
        tmp = tempfile.mkdtemp(prefix="junter-empty-")
        try:
            layout = exporter.DataLayout(tmp)
            snap, warn = exporter.build_snapshot(layout)
            self.assertEqual(snap["snapshot_kind"], "missing")
            self.assertEqual(snap["pipeline"], [])
            self.assertEqual(len(warn.issues), 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_real_mode_without_digests_emits_empty_digests_with_warning(self):
        tmp = tempfile.mkdtemp(prefix="junter-nodig-")
        try:
            headers = [
                "id", "date_found", "company", "role", "source", "url",
                "fit_score", "routed", "draft_path", "status",
                "status_date", "notes",
            ]
            rows = [["1", "2026-09-17", "X", "PM", "HN", "u", "7",
                     "ping", "", "pinged", "2026-09-17", ""]]
            _write_tracker(tmp, headers, rows)
            layout = exporter.DataLayout(tmp)
            snap, warn = exporter.build_snapshot(layout)
            self.assertEqual(snap["digests"], [])
            self.assertTrue(any(
                "digests" in w["where"] for w in warn.issues
            ))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------------------
# Tests — atomic write & parse_warnings.json
# ----------------------------------------------------------------------------

class OutputTests(unittest.TestCase):

    def test_atomic_write_replaces_target(self):
        tmp = tempfile.mkdtemp(prefix="junter-atom-")
        try:
            seed = _make_seed_snapshot()
            _write_seed(tmp, seed)
            target = os.path.join(tmp, "snap.json")
            # Write a sentinel first; exporter must overwrite atomically.
            with open(target, "w") as f:
                f.write("SENTINEL")
            rc = exporter.main([
                "--data-dir", tmp,
                "--out", target,
                "--no-warnings",
            ])
            self.assertEqual(rc, 0)
            with open(target, "r") as f:
                content = f.read()
            self.assertNotIn("SENTINEL", content)
            parsed = json.loads(content)
            self.assertEqual(parsed["snapshot_kind"], "synthetic")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_warnings_dumped_alongside_snapshot(self):
        tmp = tempfile.mkdtemp(prefix="junter-warn-")
        try:
            # Synthetic mode: warnings SHOULD be written to parse_warnings.json.
            seed = _make_seed_snapshot()
            _write_seed(tmp, seed)
            warnings_path = os.path.join(tmp, "parse_warnings.json")
            # Synthetic seed should produce zero warnings, so the file
            # must NOT be written (clean-dir discipline).
            exporter.main(["--data-dir", tmp, "--out",
                           os.path.join(tmp, "snap.json")])
            self.assertFalse(os.path.exists(warnings_path))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_real_mode_does_not_write_into_real_tree(self):
        """The exporter must NOT write parse_warnings.json when the
        JUNTER_DATA_DIR points at the real engine tree — that directory
        is owned by Track 1. Warnings go to stderr instead.
        """
        tmp = tempfile.mkdtemp(prefix="junter-realwarn-")
        try:
            headers = [
                "id", "date_found", "company", "role", "source", "url",
                "fit_score", "routed", "draft_path", "status",
                "status_date", "notes",
            ]
            rows = [["1", "2026-09-17", "X", "PM", "HN", "u", "BAD",
                     "ping", "", "pinged", "2026-09-17", ""]]
            _write_tracker(tmp, headers, rows)
            warnings_path = os.path.join(tmp, "parse_warnings.json")
            self.assertFalse(os.path.exists(warnings_path))
            # Capture stderr to verify warnings were emitted there.
            import io
            from contextlib import redirect_stderr
            err = io.StringIO()
            with redirect_stderr(err):
                rc = exporter.main([
                    "--data-dir", tmp,
                    "--out", os.path.join(tmp, "snap.json"),
                ])
            self.assertEqual(rc, 0)
            self.assertFalse(os.path.exists(warnings_path),
                             "must not write parse_warnings.json into "
                             "the real engine tree")
            self.assertIn("parse_warnings", err.getvalue())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------------------
# Tests — main() end-to-end against the real synthetic seed on disk
# ----------------------------------------------------------------------------

class EndToEndSyntheticTests(unittest.TestCase):

    def test_main_runs_against_repo_seed_json(self):
        """If the project's synthetic-data/seed.json exists, `export.py`
        in synthetic mode should reproduce it intact. We use --no-warnings
        so we don't litter the real data dir with warnings.
        """
        seed_path = os.path.join(ROOT, "synthetic-data", "seed.json")
        if not os.path.isfile(seed_path):
            self.skipTest("synthetic-data/seed.json not present; "
                          "run `python3 synthetic-data/generate.py` first")

        # Capture stdout via redirect.
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = exporter.main(["--data-dir", os.path.dirname(seed_path),
                                "--no-warnings"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        parsed = json.loads(out)
        self.assertEqual(parsed["snapshot_kind"], "synthetic")
        self.assertEqual(len(parsed["pipeline"]), 50)
        # Deadline rail must reflect the seed's >=3 deadlines.
        self.assertGreaterEqual(len(parsed["deadline_rail"]), 3)
        # Role detail must be keyed by id (string).
        self.assertTrue(all(isinstance(k, str) for k in parsed["role_detail"].keys()))


if __name__ == "__main__":
    unittest.main()

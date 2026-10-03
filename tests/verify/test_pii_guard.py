"""Privacy gate for every JSON payload committed to the public demo."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests.verify._helpers import ROOT, SEED, actionable

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
NON_EXAMPLE_URL = re.compile(r"https?://(?!example\.com)[^\s\"']+", re.I)


def reasons(text: str):
    return (["real email"] if EMAIL.search(text) else []) + (["non-example.com URL"] if NON_EXAMPLE_URL.search(text) else [])


class PiiGuardTests(unittest.TestCase):
    def test_synthetic_seed_is_valid_and_pii_safe(self):
        raw = SEED.read_text(encoding="utf-8")
        json.loads(raw)
        found = reasons(raw)
        if found:
            actionable(self, SEED, found[0], found, [], "replace personal data with synthetic copy or example.com URLs")

    def test_all_committed_json_payloads_are_safe(self):
        # Only committed JSON may be deployed. Ignore package lock/config and Figma
        # metadata because neither is served by /api/data or the static UI.
        payloads = [path for path in ROOT.rglob("*.json") if ".git" not in path.parts and path.name not in {"package.json", "package-lock.json", "export.json"}]
        self.assertIn(SEED, payloads, "synthetic-data/seed.json missing from deployable payload inventory")
        for path in payloads:
            raw = path.read_text(encoding="utf-8")
            try:
                json.loads(raw)
            except json.JSONDecodeError as exc:
                actionable(self, path, "", f"invalid JSON: {exc}", "valid JSON", "repair the payload before serving it")
            found = reasons(raw)
            if found:
                actionable(self, path, found[0], found, [], "remove PII or use fictional/example.com fixture data")

    def test_inline_fallback_has_no_pii_guard_trigger(self):
        app = ROOT / "ui" / "app.js"
        source = app.read_text(encoding="utf-8")
        start, end = source.find("var FALLBACK"), source.find("function normalizeState")
        self.assertGreaterEqual(start, 0, "ui/app.js: FALLBACK fixture missing")
        fallback = source[start:end if end > start else None]
        found = reasons(fallback)
        if found:
            actionable(self, app, found[0], found, [], "replace fallback contacts/links with fictional data")

    def test_real_tracker_sample_is_not_committed(self):
        forbidden = [ROOT / "tracker.csv", ROOT / "real-tracker-sample.json", ROOT / "fixtures" / "real-tracker-sample.json"]
        committed = [path for path in forbidden if path.exists()]
        self.assertEqual(committed, [], f"{committed}: real tracker samples must not enter the public repository\nfix: remove the file and test only synthetic fixtures")

    def test_runtime_guard_is_present_for_defense_in_depth(self):
        app = ROOT / "ui" / "app.js"
        source = app.read_text(encoding="utf-8")
        for marker in ("looks_like_pii", "PII", "example.com"):
            self.assertIn(marker, source, f"ui/app.js: runtime PII defense missing marker {marker!r}; restore the client-side guard")


if __name__ == "__main__":
    unittest.main()

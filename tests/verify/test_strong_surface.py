"""Proves that Junter's five product mechanisms are visible in rendered UI code."""
from __future__ import annotations

import unittest

from tests.verify._helpers import UI, actionable, normalized

SURFACES = {
    "rubric explainability": ("Why this scored", "rubric-factor"),
    "refusal-to-pad": ("Rejected with reasons", "digest-rejected"),
    "deadline-first": ("Deadline Rail", "rail-tier"),
    "local-first privacy": ("synthetic", "public"),
    "spec-as-code": ("Reweighting only happens when interaction data exists", "Rubric & Calibration"),
}


class StrongSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = UI / "app.js"
        cls.css = UI / "styles.css"
        cls.source = cls.app.read_text(encoding="utf-8") + (UI / "index.html").read_text(encoding="utf-8")
        cls.normalized_source = normalized(cls.source)

    def _assert_visible(self, strength):
        text, element = SURFACES[strength]
        if normalized(text) not in self.normalized_source:
            actionable(self, self.app, text, "named UI copy missing", text, f"render the {strength} copy in its named UI element")
        if normalized(element) not in self.normalized_source and normalized(element) not in normalized(self.css.read_text(encoding="utf-8")):
            actionable(self, self.app, element, "named UI element missing", element, f"add the documented {strength} element/class")

    def test_rubric_explainability_surface(self): self._assert_visible("rubric explainability")
    def test_refusal_to_pad_surface(self): self._assert_visible("refusal-to-pad")
    def test_deadline_first_surface(self): self._assert_visible("deadline-first")
    def test_local_first_privacy_surface(self): self._assert_visible("local-first privacy")
    def test_spec_as_code_surface(self): self._assert_visible("spec-as-code")


if __name__ == "__main__":
    unittest.main()

"""Figma → HTML parity gate for the approved 11-screen export.

The parity corpus is intentionally semantic: frame names and their documented
screen-intent anchors are stable product copy, unlike live role names/counts.
"""
from __future__ import annotations

import json
import unittest

from tests.verify._helpers import FIGMA_EXPORT, UI, actionable, normalized

INTENT_ANCHORS = {
    "pipeline": ["Pipeline", "Interested"], "deadline": ["Deadline", "days"],
    "focus": ["Focus", "gate"], "digest": ["Daily Digest", "Rejected"],
    "run-health": ["Run Health", "Cron"], "rubric": ["Rubric", "Reweighting"],
    "telegram": ["Telegram", "Failed"], "role-detail": ["Why this scored", "History"],
    "backgrounder": ["Application Strategy", "Skill Gap"], "boards": ["Job Boards", "Pipeline"],
    "research": ["Research", "Calibration"],
}


class FigmaParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.export = json.loads(FIGMA_EXPORT.read_text(encoding="utf-8"))
        cls.html = (UI / "index.html").read_text(encoding="utf-8")
        cls.render = (UI / "app.js").read_text(encoding="utf-8")
        cls.source = cls.html + cls.render

    def test_export_has_exactly_eleven_canonical_frames(self):
        screens = self.export.get("screens", [])
        self.assertEqual(len(screens), 11, "docs/ui-evidence/figma-refresh-2026-10-03/export.json: expected 11 canonical frames; fix the approved export")
        self.assertEqual({s["slug"] for s in screens}, set(INTENT_ANCHORS), "export.json: frame slugs drifted; update the explicit parity mapping")

    def test_section_names_match_the_html_render(self):
        for screen in self.export["screens"]:
            name = screen["name"]
            if normalized(name) not in normalized(self.source):
                actionable(self, UI / "app.js", name, "missing rendered section", name, "render this Figma frame name in the matching route")

    def test_color_token_inventory_matches_css_exactly(self):
        css = (UI / "styles.css").read_text(encoding="utf-8").upper()
        actual = set(__import__("re").findall(r"#[0-9A-F]{6}", css))
        expected = set(self.export["tokens"]["colors"])
        self.assertEqual(actual, expected, f"ui/styles.css: color inventory differs\nactual: {sorted(actual)}\nexpected: {sorted(expected)}\nfix: use only the approved Figma token palette")

    def test_text_parity_is_100_percent_for_stable_section_names(self):
        names = [screen["name"] for screen in self.export["screens"]]
        exact = sum(normalized(name) in normalized(self.source) for name in names)
        ratio = exact / len(names)
        self.assertGreaterEqual(ratio, .95, f"ui/app.js: section-name parity is {ratio:.0%}, below 95%\nfix: use the approved Figma section names in render functions")

    def test_all_frame_intents_have_rendered_anchors(self):
        normalized_source = normalized(self.source)
        for slug, anchors in INTENT_ANCHORS.items():
            for anchor in anchors:
                if normalized(anchor) not in normalized_source:
                    actionable(self, UI / "app.js", slug, "missing intent anchor", anchor, "render the documented product intent on this screen")


if __name__ == "__main__":
    unittest.main()

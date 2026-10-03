"""Golden screenshot regression gate for the eleven approved product screens."""
from __future__ import annotations

import os
import unittest
from pathlib import Path

from tests.verify._helpers import DOCS, FIGMA_EXPORT, pixel_diff_percent

GOLDEN = DOCS / "ui-evidence" / "golden"
CURRENT = Path(os.environ.get("JUNTER_VISUAL_CURRENT_DIR", str(DOCS / "ui-evidence" / "current")))


class VisualRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        cls.screens = [screen["slug"] for screen in json.loads(FIGMA_EXPORT.read_text(encoding="utf-8"))["screens"]]

    def test_all_eleven_golden_images_exist(self):
        missing = [slug for slug in self.screens if not (GOLDEN / f"{slug}.png").is_file()]
        self.assertEqual(missing, [], f"docs/ui-evidence/golden: missing {missing}\nfix: approve and add one 1440px baseline per canonical screen")

    def test_all_eleven_current_images_exist(self):
        missing = [slug for slug in self.screens if not (CURRENT / f"{slug}.png").is_file()]
        self.assertEqual(missing, [], f"{CURRENT}: missing {missing}\nfix: capture each current HTML route before running the visual gate")

    def test_each_current_image_matches_viewport(self):
        for slug in self.screens:
            # pixel_diff_percent checks size before comparing pixels.
            try:
                pixel_diff_percent(CURRENT / f"{slug}.png", GOLDEN / f"{slug}.png")
            except AssertionError as exc:
                if "actual:" in str(exc) and "expected:" in str(exc):
                    raise

    def test_each_screen_stays_within_five_percent_pixel_difference(self):
        for slug in self.screens:
            actual = pixel_diff_percent(CURRENT / f"{slug}.png", GOLDEN / f"{slug}.png")
            self.assertLessEqual(actual, 5.0, f"docs/ui-evidence/current/{slug}.png: pixel diff {actual:.2f}% exceeds 5.00%\nfix: inspect the route at the approved viewport and update intentional golden changes with review")


if __name__ == "__main__":
    unittest.main()

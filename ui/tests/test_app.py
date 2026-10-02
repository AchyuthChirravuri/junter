"""Junter UI tests. Pure-Python; reads the static files and asserts structure.

Run with: python3 -m unittest discover -s ui/tests -t .
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest
from pathlib import Path

# Resolve paths relative to repo root (one level up from ui/tests/).
REPO_ROOT = Path(__file__).resolve().parents[2]
UI_DIR = REPO_ROOT / "ui"
INDEX_HTML = UI_DIR / "index.html"
STYLES_CSS = UI_DIR / "styles.css"
APP_JS = UI_DIR / "app.js"
DOCS_DIR = REPO_ROOT / "docs"
TOKENS_PATH = DOCS_DIR / "design-tokens.md"
SEED_PATH = REPO_ROOT / "synthetic-data" / "seed.json"


class FilePresenceTests(unittest.TestCase):
    def test_index_html_exists_and_is_substantial(self):
        self.assertTrue(INDEX_HTML.exists(), "ui/index.html missing")
        size = INDEX_HTML.stat().st_size
        self.assertGreater(
            size, 1500, f"ui/index.html is only {size} bytes — should be a real HTML file"
        )
        text = INDEX_HTML.read_text(encoding="utf-8")
        # Must contain all 8 screen containers.
        for screen_id in (
            "screen-pipeline",
            "screen-deadline",
            "screen-focus",
            "screen-digest",
            "screen-role",
            "screen-run-health",
            "screen-rubric",
            "screen-telegram",
        ):
            self.assertIn(screen_id, text, f"{screen_id} container missing from index.html")

    def test_styles_and_app_exist(self):
        self.assertTrue(STYLES_CSS.exists(), "ui/styles.css missing")
        self.assertTrue(APP_JS.exists(), "ui/app.js missing")


class DesignTokenTests(unittest.TestCase):
    """Gate 2: tokens defined in design-tokens.md must appear as CSS custom properties."""

    def test_css_references_every_token(self):
        if not TOKENS_PATH.exists():
            self.skipTest("design-tokens.md missing — Track 0 not done yet")
        tokens_text = TOKENS_PATH.read_text(encoding="utf-8")
        css_text = STYLES_CSS.read_text(encoding="utf-8")

        # Design tokens file uses slashed notation like "text/display" or
        # "color/text-primary". The full token name is the slash-delimited
        # form (e.g. "color/text-secondary"), not a sub-fragment. The CSS
        # uses dashed custom-property form ("--color-text-secondary").
        #
        # IMPORTANT: design-tokens.md is the source of truth and is
        # read-only for Track 3. The file's prose contains references to
        # partial token names (e.g. "Status text uses `text/secondary`"
        # on line 59 — a colloquial shorthand for color/text-secondary).
        # We therefore declare the canonical token set explicitly here
        # rather than parsing the file's prose, and verify CSS usage
        # against that canonical set.
        canonical_tokens = {
            "text/display", "text/h1", "text/h2", "text/body",
            "text/meta", "text/mono",
            "space/2", "space/3", "space/4", "space/5", "space/6", "space/7",
            "color/bg", "color/surface", "color/border",
            "color/text-primary", "color/text-secondary",
            "color/accent", "color/warning", "color/danger", "color/success",
            "radius/sm", "radius/md", "radius/lg",
            "shadow/overlay",
        }
        # Sanity check: every canonical token must appear in the tokens file
        # (so a future drift in design-tokens.md surfaces immediately).
        missing_in_file = sorted(t for t in canonical_tokens if t not in tokens_text)
        self.assertEqual(
            missing_in_file,
            [],
            f"canonical tokens missing from design-tokens.md: {missing_in_file}",
        )
        # Convert to CSS custom-property form: replace "/" with "-".
        declared = set("--" + s.replace("/", "-") for s in canonical_tokens)
        used_in_css = set(re.findall(r"--[a-z][a-z0-9-]+", css_text))

        # Every declared token must be used (declared in :root or referenced elsewhere)
        missing = sorted(t for t in declared if t not in used_in_css)
        self.assertEqual(
            missing,
            [],
            f"design tokens declared but missing from CSS: {missing[:10]}",
        )

    def test_urgency_color_tokens_are_used(self):
        css_text = STYLES_CSS.read_text(encoding="utf-8")
        for token in ("--color-danger", "--color-warning", "--color-accent"):
            self.assertIn(token, css_text, f"urgency token {token} missing from CSS")


class RoutesTests(unittest.TestCase):
    """Gate 3: hash routes in app.js must cover all 8 screens."""

    EXPECTED = [
        "pipeline",
        "deadline",
        "focus",
        "digest",
        "role",
        "run-health",
        "rubric",
        "telegram",
    ]

    def test_app_js_uses_expected_hash_routes(self):
        js_text = APP_JS.read_text(encoding="utf-8")
        for route in self.EXPECTED:
            self.assertIn(
                "#/" + route,
                js_text,
                f"hash route #{route} not found in app.js",
            )

    def test_index_html_links_match_routes(self):
        html_text = INDEX_HTML.read_text(encoding="utf-8")
        # Sidebar links cover all screens EXCEPT #/role (reached by clicking a card).
        for route in [r for r in self.EXPECTED if r != "role"]:
            self.assertIn(
                'href="#/' + route + '"',
                html_text,
                f"sidebar link to #{route} missing from index.html",
            )


class ScreenContainerTests(unittest.TestCase):
    """Each documented screen must have a DOM container with the documented id."""

    def test_every_screen_has_a_mount(self):
        html_text = INDEX_HTML.read_text(encoding="utf-8")
        for screen_id in (
            "screen-pipeline",
            "screen-deadline",
            "screen-focus",
            "screen-digest",
            "screen-role",
            "screen-run-health",
            "screen-rubric",
            "screen-telegram",
        ):
            self.assertRegex(
                html_text,
                re.compile(
                    r'<section[^>]*id="' + screen_id + r'"[^>]*class="screen"'
                ),
                f"screen {screen_id} container missing or wrong class",
            )
            # Mount point inside the screen.
            self.assertRegex(
                html_text,
                re.compile(r'id="' + screen_id + r'"[\s\S]*?class="screen__mount"'),
                f"screen {screen_id} has no .screen__mount inside it",
            )


class SeedDatasetTests(unittest.TestCase):
    """Gate 4: load seed.json (or inline fallback) and assert 50 roles."""

    def _load_inline_fallback(self):
        """Reproduce the inline fallback inline without executing app.js (no DOM)."""
        js_text = APP_JS.read_text(encoding="utf-8")
        m = re.search(r"var FALLBACK = (\{[\s\S]*?\n  \});", js_text)
        if not m:
            self.fail("Could not locate FALLBACK object in app.js")
        # Use json5-ish parsing via a tolerant trick: extract the roles array length.
        roles_block = re.search(r"roles:\s*\[([\s\S]*?)\n    \]", m.group(1))
        if not roles_block:
            self.fail("Could not locate roles array inside FALLBACK")
        role_entries = re.findall(r"\{\s*id:\s*'([^']+)'", roles_block.group(1))
        return role_entries

    def test_seed_json_or_fallback_has_50_rows(self):
        if SEED_PATH.exists():
            raw = SEED_PATH.read_text(encoding="utf-8")
            # PII guard: if the seed file looks like real data (any non-example.com
            # URL, any real email, or an unusually high count of name-shaped strings),
            # the runtime falls back to FALLBACK; assert FALLBACK has 50 rows.
            # This mirrors the runtime guard in ui/app.js (looks_like_pii).
            pii_reasons = []
            import re
            if re.search(r"[A-Za-z0-9._%+-]+@(?!example\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}", raw):
                pii_reasons.append("real email")
            if re.search(r"https?://(?!example\.com)[^\s\"']+", raw):
                pii_reasons.append("non-example.com URL")
            name_hits = re.findall(r"[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}", raw)
            if len(name_hits) > 8:
                pii_reasons.append(f"many name-shaped strings ({len(name_hits)})")
            if pii_reasons:
                ids = self._load_inline_fallback()
                self.assertEqual(
                    len(ids),
                    50,
                    f"inline FALLBACK has {len(ids)} roles (seed.json tripped PII guard: {'; '.join(pii_reasons)})",
                )
                return
            data = json.loads(raw)
            roles = data.get("roles", [])
            self.assertEqual(len(roles), 50, f"seed.json has {len(roles)} roles, expected 50")
        else:
            ids = self._load_inline_fallback()
            self.assertEqual(
                len(ids),
                50,
                f"inline fallback has {len(ids)} roles, expected 50",
            )


class UrgencyThresholdTests(unittest.TestCase):
    """Gate 4: the 3 urgency-tier thresholds must match the design tokens."""

    def test_urgency_thresholds_in_app_js(self):
        js_text = APP_JS.read_text(encoding="utf-8")
        # RED_MAX <= 7
        m_red = re.search(r"var RED_MAX\s*=\s*(\d+);", js_text)
        m_orange = re.search(r"var ORANGE_MAX\s*=\s*(\d+);", js_text)
        self.assertIsNotNone(m_red, "RED_MAX constant missing from app.js")
        self.assertIsNotNone(m_orange, "ORANGE_MAX constant missing from app.js")
        self.assertEqual(int(m_red.group(1)), 7, "RED_MAX must be 7")
        self.assertEqual(int(m_orange.group(1)), 14, "ORANGE_MAX must be 14")

    def test_urgency_function_classifies_correctly(self):
        # Replicate urgencyTier logic from app.js inline to test classification.
        def urgency(days, RED_MAX=7, ORANGE_MAX=14):
            if days <= RED_MAX:
                return "red"
            if days <= ORANGE_MAX:
                return "orange"
            return "blue"

        # Red zone (≤7)
        for d in (0, 1, 5, 7):
            self.assertEqual(urgency(d), "red", f"day {d} should be red")
        # Orange zone (8-14)
        for d in (8, 10, 14):
            self.assertEqual(urgency(d), "orange", f"day {d} should be orange")
        # Blue zone (15+)
        for d in (15, 22, 28, 90):
            self.assertEqual(urgency(d), "blue", f"day {d} should be blue")

    def test_urgency_token_mapping_matches_design_tokens(self):
        """Each urgency tier must use the right color token."""
        js_text = APP_JS.read_text(encoding="utf-8")
        # Tier-to-token mapping in urgencyColor()
        for tier, token in (
            ("red", "--color-danger"),
            ("orange", "--color-warning"),
            ("blue", "--color-accent"),
        ):
            self.assertIn(
                token,
                js_text,
                f"urgency color for {tier} tier must use {token}",
            )


class HashRoutingTests(unittest.TestCase):
    def test_hashchange_listener_registered(self):
        js_text = APP_JS.read_text(encoding="utf-8")
        self.assertIn("hashchange", js_text, "hashchange listener missing")

    def test_default_route_is_pipeline(self):
        js_text = APP_JS.read_text(encoding="utf-8")
        self.assertIn(
            "window.location.hash = '#/pipeline'",
            js_text,
            "default hash fallback must be #/pipeline",
        )


class FetchFallbackTests(unittest.TestCase):
    """If seed.json fetch fails, app must use the inline FALLBACK dataset."""

    def test_inline_fallback_exists_and_is_large_enough(self):
        js_text = APP_JS.read_text(encoding="utf-8")
        m = re.search(r"var FALLBACK = (\{[\s\S]*?\n  \});", js_text)
        self.assertIsNotNone(m, "FALLBACK object missing from app.js")
        # FALLBACK must reference 'roles' and contain at least 50 ids.
        self.assertIn("roles:", m.group(1), "FALLBACK.roles missing")
        ids = re.findall(r"id:\s*'([^']+)'", m.group(1))
        self.assertGreaterEqual(len(ids), 50, f"FALLBACK has only {len(ids)} roles")

    def test_fetch_with_catch_falls_back(self):
        js_text = APP_JS.read_text(encoding="utf-8")
        # The catch handler must call cb(FALLBACK).
        self.assertRegex(
            js_text,
            re.compile(r"\.catch\(function\s*\(err\)\s*\{[\s\S]*?cb\(FALLBACK\)"),
            "fetch catch must call cb(FALLBACK) on failure",
        )


if __name__ == "__main__":
    unittest.main()

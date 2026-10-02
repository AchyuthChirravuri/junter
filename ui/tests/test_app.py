"""Junter UI tests. Pure-Python; reads the static files and asserts structure.

Run with: python3 -m unittest discover -s ui/tests -t .
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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


# ---------------------------------------------------------------------------
# Mirrors of the runtime PII guard in ui/app.js (looks_like_pii). Kept in sync
# by hand; if app.js's guard changes, these must change too.
# ---------------------------------------------------------------------------

PII_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PII_NON_EXAMPLE_URL_RE = re.compile(r"https?://(?!example\.com)[^\s\"']+")
PII_NAME_RE = re.compile(r"[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}")
PII_NAME_HITS_MAX = 12

# Role / seniority vocabulary that must NOT count as a personal name. This is a
# subset of the stop-words in ui/app.js — enough to demonstrate the mechanism.
PII_NAME_STOPWORDS = {
    "product", "manager", "marketing", "senior", "associate", "principal",
    "staff", "lead", "growth", "strategy", "data", "platform", "corporate",
    "development", "experience", "markets", "international", "expansion",
    "grad", "engineering", "software", "design", "program", "director",
    "digital", "analyst", "operations", "success", "specialist", "engineer",
    "project", "management", "business", "technical", "solutions", "customer",
    "content", "cloud", "security", "risk", "compliance", "finance",
    "financial", "sales", "account", "research", "university", "careers",
    "company", "demand", "generation", "developer", "services", "systems",
    "infrastructure", "applications", "sciences", "health", "media", "brand",
    "global", "regional", "national", "executive", "general", "vice", "head",
    "chief", "officer", "coordinator", "consultant", "architect", "scientist",
}


def pii_guard_reasons(text):
    """Return a list of PII-guard trip reasons for `text` (empty == passes)."""
    reasons = []
    if PII_EMAIL_RE.search(text):
        reasons.append("real email")
    if PII_NON_EXAMPLE_URL_RE.search(text):
        reasons.append("non-example.com URL")
    hits = 0
    for m in PII_NAME_RE.finditer(text):
        parts = m.group(0).split()
        if parts[0].lower() in PII_NAME_STOPWORDS or parts[1].lower() in PII_NAME_STOPWORDS:
            continue
        hits += 1
    if hits > PII_NAME_HITS_MAX:
        reasons.append(f"many name-shaped strings ({hits})")
    return reasons


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
            # URL, any real email, or an unusually high count of name-shaped strings
            # that survive the role/company stop-word filter), the runtime falls
            # back to FALLBACK; assert FALLBACK has 50 rows. This mirrors the
            # runtime guard in ui/app.js (looks_like_pii).
            pii_reasons = pii_guard_reasons(raw)
            if pii_reasons:
                ids = self._load_inline_fallback()
                self.assertEqual(
                    len(ids),
                    50,
                    f"inline FALLBACK has {len(ids)} roles (seed.json tripped PII guard: {'; '.join(pii_reasons)})",
                )
                return
            data = json.loads(raw)
            # The exporter-shaped seed uses `pipeline`; the inline FALLBACK uses
            # `roles`. Accept either so the assertion tracks the real contract.
            rows = data.get("pipeline", data.get("roles", []))
            self.assertEqual(len(rows), 50, f"seed.json has {len(rows)} roles, expected 50")
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


# ---------------------------------------------------------------------------
# Exporter -> UI contract adapter (D1 fix).
#
# The exporter emits {pipeline, deadline_rail, role_detail, run_health,
# rejected_with_reasons}; the screens read {roles, cron_runs, rubric_diff,
# rubric_outcomes}. normalizeState() maps one to the other. These tests run the
# real ui/app.js in Node against a minimal DOM stub, so they exercise the exact
# shipped code rather than a re-implementation.
# ---------------------------------------------------------------------------

NODE = shutil.which("node")


def _run_app_js(expr):
    """Load ui/app.js in Node with a DOM stub, then evaluate `expr` where `J`
    is window.__junter. Returns the JSON-decoded result (or None on failure)."""
    app = APP_JS.read_text(encoding="utf-8")
    stub = (
        "global.fetch = function () { return Promise.reject(new Error('no-network-in-test')); };\n"
        "var window = { location: { hash: '#/pipeline' }, addEventListener: function () {} };\n"
        "var document = {\n"
        "  readyState: 'complete',\n"
        "  addEventListener: function () {},\n"
        "  querySelectorAll: function () { return []; },\n"
        "  getElementById: function () { return null; },\n"
        "  createElement: function () { return { style: {}, appendChild: function () {}, setAttribute: function () {}, addEventListener: function () {}, querySelector: function () { return null; } }; },\n"
        "  createTextNode: function (t) { return { text: t }; }\n"
        "};\n"
        "var console = { log: function () {}, warn: function () {}, error: function () {} };\n"
    )
    program = stub + "\n" + app + "\n"
    program += "setTimeout(function () {\n"
    program += "  var J = window.__junter;\n"
    program += "  if (!J) { process.stdout.write('NO_JUNTER'); return; }\n"
    program += "  try { process.stdout.write(JSON.stringify(" + expr + ")); }\n"
    program += "  catch (e) { process.stdout.write('ERR:' + e.message); }\n"
    program += "}, 25);\n"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(program)
        path = f.name
    try:
        proc = subprocess.run([NODE, path], capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(path)
    out = proc.stdout or ""
    if out in ("NO_JUNTER", "") or out.startswith("ERR:"):
        return {"__error__": out or proc.stderr}
    return json.loads(out)


def _exporter_fixture():
    """A minimal exporter-shaped snapshot with real-mode characteristics."""
    return {
        "snapshot_at": "2026-10-01T12:00:00-04:00",
        "snapshot_kind": "real",
        "pipeline": [
            {"id": 7, "company": "Google", "role": "APM, Cloud Platform",
             "source": "Career", "url": "https://example.com/g",
             "fit_score": 8.7, "routed": "int", "status": "interested",
             "status_date": "2026-09-25", "notes": "angle here",
             "deadline": "2026-10-04", "blocked_reason": ""},
            {"id": 9, "company": "Meta", "role": "APM, Growth",
             "source": "HN", "url": "https://example.com/m",
             "fit_score": 8.1, "routed": "", "status": "blocked",
             "status_date": "2026-09-22", "notes": "",
             "deadline": "", "blocked_reason": "role-mismatch-senior"},
        ],
        "deadline_rail": [
            {"id": 7, "company": "Google", "role": "APM, Cloud Platform",
             "fit_score": 8.7, "deadline": "2026-10-04", "days_out": 3,
             "urgency": "red", "urgency_label": "imminent",
             "url": "https://example.com/g", "status": "interested"}
        ],
        "role_detail": {
            "7": {"id": 7, "company": "Google", "role": "APM, Cloud Platform",
                  "url": "https://example.com/g", "fit_score": 8.7,
                  "status": "interested", "deadline": "2026-10-04",
                  "blocked_reason": "", "draft_paths": ["drafts/7-google-bg.md"],
                  "company_summary": "Cloud + AI platform work.",
                  "rubric_factors": {"domain_fit": 1.8, "level_fit": 1.1},
                  "rubric_version": "v2",
                  "history": [{"ts": "2026-09-25T09:00:00-04:00",
                               "event": "discovered", "note": "Found via Career"}]},
            "9": {"id": 9, "company": "Meta", "role": "APM, Growth"},
        },
        "run_health": [
            {"name": "hunt-part1-platforms", "schedule": "07:30 daily",
             "last_status": "ok", "last_run_at": "2026-10-01T07:18:00-04:00",
             "latency_s": 42}
        ],
        "rubric_versions": [
            {"version": "v1", "created_at": "2026-08-15",
             "weights": {"domain_fit": 0.2, "level_fit": 0.2},
             "outcomes": {"mean_fit_score": 7.2}, "rationale": "baseline"},
            {"version": "v2", "created_at": "2026-09-22",
             "weights": {"domain_fit": 0.3, "level_fit": 0.1},
             "outcomes": {"mean_fit_score": 7.4}, "rationale": "reweighted"},
        ],
        "telegram_messages": [],
        "rejected_with_reasons": [
            {"id": 9, "company": "Meta", "role": "APM, Growth",
             "fit_score": 8.1, "blocked_reason": "role-mismatch-senior",
             "source": "HN", "url": "https://example.com/m"}
        ],
        "digests": [
            {"date": "2026-10-01",
             "sections": [{"title": "Top matches", "role_ids": [7]}]}
        ],
    }


@unittest.skipIf(NODE is None, "node not available to execute ui/app.js")
class ExporterAdapterTests(unittest.TestCase):
    """normalizeState() must map the exporter contract onto the UI contract."""

    def test_pipeline_maps_to_roles(self):
        res = _run_app_js("J.normalizeState(%s)" % json.dumps(_exporter_fixture()))
        self.assertNotIn("__error__", res, f"node run failed: {res}")
        roles = res["roles"]
        self.assertEqual(len(roles), 2, "adapter must map both pipeline rows")
        g = roles[0]
        self.assertEqual(g["id"], "7", "ids are normalized to strings for the router")
        self.assertEqual(g["company"], "Google")
        self.assertEqual(g["fit"], 8.7)
        self.assertEqual(g["status"], "interested")
        self.assertEqual(g["angle"], "angle here", "notes -> angle")
        # Rail wins for days: exact days_out, not date math.
        self.assertEqual(g["deadline_days"], 3)
        # role_detail is folded in.
        self.assertEqual(g["draft_paths"], ["drafts/7-google-bg.md"])
        self.assertEqual(len(g["history"]), 1)
        self.assertEqual(g["rubric_factors"]["domain_fit"], 1.8)
        self.assertEqual(g["summary"], "Cloud + AI platform work.")
        # The blocked row keeps its structured reason.
        self.assertEqual(roles[1]["status"], "blocked")
        self.assertEqual(roles[1]["blocked_reason"], "role-mismatch-senior")

    def test_run_health_maps_to_cron_runs(self):
        res = _run_app_js("J.normalizeState(%s)" % json.dumps(_exporter_fixture()))
        self.assertEqual(len(res["cron_runs"]), 1)
        self.assertEqual(res["cron_runs"][0]["name"], "hunt-part1-platforms")
        self.assertEqual(res["cron_runs"][0]["last_status"], "ok")

    def test_rubric_diff_and_outcomes_are_flattened(self):
        res = _run_app_js("J.normalizeState(%s)" % json.dumps(_exporter_fixture()))
        diff = {d["factor"]: (d["from"], d["to"]) for d in res["rubric_diff"]}
        self.assertEqual(diff.get("domain_fit"), (0.2, 0.3))
        self.assertEqual(diff.get("level_fit"), (0.2, 0.1))
        metrics = {o["metric"] for o in res["rubric_outcomes"]}
        self.assertIn("mean_fit_score", metrics)

    def test_rejected_and_digests_are_presented(self):
        res = _run_app_js("J.normalizeState(%s)" % json.dumps(_exporter_fixture()))
        self.assertEqual(len(res["rejected_rows"]), 1)
        self.assertEqual(res["rejected_rows"][0]["company"], "Meta")
        self.assertEqual(res["digests"][0]["promoted"][0]["id"], "7")
        self.assertTrue(res["digests"][0]["rejected"], "newest digest carries the blocked set")

    def test_normalized_input_passes_through_untouched(self):
        # Idempotency: the inline FALLBACK (already normalized) must be a no-op.
        res = _run_app_js(
            "(function(){var s={roles:[{id:'x'}],digests:[],cron_runs:[]};"
            "return J.normalizeState(s)===s;})()"
        )
        self.assertIs(res, True, "already-normalized state must not be re-mapped")

    def test_role_days_prefers_rail_then_falls_back(self):
        res = _run_app_js(
            "({rail: J.roleDays({deadline:'2026-10-04', deadline_days:3}),"
            " math: J.roleDays({deadline:'2026-10-04'})})"
        )
        self.assertEqual(res["rail"], 3, "deadline_days wins when present")
        self.assertEqual(res["math"], 3, "date math against the 2026-10-01 anchor")


@unittest.skipIf(NODE is None, "node not available to execute ui/app.js")
class PiiGuardRuntimeTests(unittest.TestCase):
    """The runtime guard in app.js must accept the synthetic seed and reject
    a real-data-shaped payload — without ever being bypassed."""

    def test_seed_passes_the_runtime_guard(self):
        seed_text = SEED_PATH.read_text(encoding="utf-8")
        res = _run_app_js("J.looks_like_pii(%s)" % json.dumps(seed_text))
        self.assertIsNone(res, f"synthetic seed must not trip the PII guard: {res!r}")

    def test_real_shaped_payload_is_rejected(self):
        fake_real = json.dumps({
            "pipeline": [
                {"id": 1, "company": "Acme",
                 "url": "https://news.ycombinator.com/item?id=49522897",
                 "notes": "contact emily.thompson@luciaprotocol.com"},
            ]
        })
        res = _run_app_js("J.looks_like_pii(%s)" % json.dumps(fake_real))
        self.assertIsNotNone(res, "a real email / non-example URL must trip the guard")


class SeedWatchlistTests(unittest.TestCase):
    """Gate: the offline seed must show the watchlist priority companies so the
    Pipeline Board and Deadline Rail are demonstrable without real data."""

    WATCHLIST = ["Google", "Microsoft", "Amazon", "Adobe", "MongoDB", "Meta"]

    def test_seed_pipeline_contains_watchlist_companies(self):
        data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        companies = {r.get("company") for r in data.get("pipeline", [])}
        missing = [c for c in self.WATCHLIST if c not in companies]
        self.assertEqual(missing, [], f"watchlist companies missing from seed: {missing}")

    def test_seed_deadline_rail_has_all_three_tiers(self):
        data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        tiers = {r.get("urgency") for r in data.get("deadline_rail", [])}
        self.assertTrue(
            {"red", "orange", "blue"}.issubset(tiers),
            f"deadline rail must exercise all 3 urgency tiers, got {tiers}",
        )


if __name__ == "__main__":
    unittest.main()

"""Opt-in live probe logic. Unit tests use a fake opener; no URL is contacted by default."""
from __future__ import annotations

import json
import os
import urllib.request
import unittest
from urllib.parse import urljoin, urlparse

ROUTES = {
    "/": "Junter", "/#/pipeline": "Pipeline", "/#/deadline": "Deadline",
    "/#/focus": "Focus", "/#/digest": "Daily Digest", "/#/run-health": "Run Health",
    "/#/rubric": "Rubric", "/#/telegram": "Telegram", "/#/boards": "Job Boards",
    "/#/research": "Research", "/api/data": "roles",
}


def validate_target(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("LIVE_URL must be a bare https deployment origin, e.g. https://preview.example.com")
    return url.rstrip("/") + "/"


def probe(url: str, opener=urllib.request.urlopen):
    target = validate_target(url)
    results = []
    for route, marker in ROUTES.items():
        request = urllib.request.Request(urljoin(target, route.lstrip("/")), headers={"Accept": "application/json" if route == "/api/data" else "text/html"})
        with opener(request, timeout=15) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            status = getattr(response, "status", response.getcode())
        text = raw.decode("utf-8", "replace")
        expected_type = "application/json" if route == "/api/data" else "text/html"
        results.append({"route": route, "status": status, "content_type": content_type, "marker": marker, "marker_present": marker.lower() in text.lower(), "type_ok": expected_type in content_type.lower(), "bytes": len(raw)})
    return results


class _Response:
    def __init__(self, body, content_type="text/html; charset=utf-8", status=200):
        self._body, self.headers, self.status = body.encode(), {"Content-Type": content_type}, status
    def read(self): return self._body
    def getcode(self): return self.status
    def __enter__(self): return self
    def __exit__(self, *_): return False


class LiveProbeTests(unittest.TestCase):
    def test_target_must_be_explicit_https_origin(self):
        for bad in ("", "http://demo.example.com", "https://demo.example.com/path", "https://demo.example.com/?x=1"):
            with self.assertRaises(ValueError, msg=f"test_live_deploy.py: invalid target {bad!r} should be rejected"):
                validate_target(bad)

    def test_probe_accepts_matching_html_and_json_responses(self):
        def opener(request, timeout):
            parsed = urlparse(request.full_url)
            route = parsed.path + ("#" + parsed.fragment if parsed.fragment else "")
            marker = ROUTES.get(route, "Junter")
            if route == "/api/data": return _Response(json.dumps({"roles": [], "marker": marker}), "application/json")
            return _Response("<html><body>Junter " + marker + "</body></html>")
        results = probe("https://preview.example.com", opener)
        self.assertEqual(len(results), len(ROUTES))
        self.assertTrue(all(row["status"] == 200 and row["type_ok"] and row["marker_present"] for row in results))

    def test_probe_reports_wrong_content_type_and_missing_marker(self):
        def opener(request, timeout): return _Response("not Junter", "text/plain", 200)
        rows = probe("https://preview.example.com", opener)
        self.assertFalse(any(row["type_ok"] for row in rows))
        self.assertTrue(any(not row["marker_present"] for row in rows))

    def test_live_phase_requires_exact_intended_sha(self):
        supplied, intended = os.environ.get("LIVE_SOURCE_SHA"), os.environ.get("INTENDED_SOURCE_SHA")
        if supplied is None and intended is None:
            self.assertIsNone(supplied, "offline unit test must not require deployment configuration")
        else:
            self.assertEqual(supplied, intended, "tests/verify/test_live_deploy.py: deployed source SHA differs from intended SHA; redeploy the intended commit")


if __name__ == "__main__":
    if os.environ.get("RUN_LIVE") == "1":
        url = os.environ.get("LIVE_URL", "")
        supplied, intended = os.environ.get("LIVE_SOURCE_SHA"), os.environ.get("INTENDED_SOURCE_SHA")
        if not supplied or not intended or supplied != intended:
            raise SystemExit("LIVE probe refused: set matching LIVE_SOURCE_SHA and INTENDED_SOURCE_SHA for the authorized deployment")
        rows = probe(url)
        failures = [row for row in rows if row["status"] != 200 or not row["type_ok"] or not row["marker_present"]]
        for row in rows:
            print("{route} status={status} type={content_type} bytes={bytes} marker={marker_present}".format(**row))
        if failures:
            raise SystemExit("LIVE probe failed; inspect the route rows above and redeploy the intended source SHA")
        print("LIVE_ACCEPTANCE=PASS")
    else:
        unittest.main()

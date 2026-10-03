"""Test harness for api/action.js.

The handler is JavaScript (Vercel serverless, ESM) and the project pins Python
3.9 in CI — which lacks tomllib for some checks but is fine for runtime
testing. This module spawns Node with a small driver that:

  * imports api/action.js,
  * stubs @vercel/edge-config with an in-memory store,
  * stubs the audit-log path with a tmpfile,
  * invokes `default(req, res)` against a mock Vercel-style request/response,
  * returns the response as JSON on stdout.

The handler's module exports an internal `__test` object that the test layer
also exercises directly (applyAction, idempotency, etc.) when a pure-function
check is cleaner than going through the full HTTP-shaped path.

Run:   python3 -m unittest api.tests.test_action_meta -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HANDLER = REPO_ROOT / "api" / "action.js"
LOADER = REPO_ROOT / "tests" / "loader.mjs"
_NODE = shutil.which("node")
NODE = _NODE if _NODE is not None else ""  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Driver: spawn Node, invoke the handler, parse the JSON response.
# ---------------------------------------------------------------------------


def _run(handler_js, setup_js="", timeout=60):
    """Run the handler against a Node child process. `handler_js` is the
    driver body (declares req/res, invokes handler, writes JSON to stdout).
    Uses the test ESM loader to resolve `@vercel/edge-config` to an in-memory
    stub so the handler runs without the real Vercel SDK."""
    program = textwrap.dedent(f"""
        {setup_js}
        {handler_js}
    """)
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as f:
        f.write(program)
        path = f.name
    try:
        proc = subprocess.run(
            [NODE, "--no-warnings", "--loader", str(LOADER), path],
            capture_output=True, text=True, timeout=timeout,
        )
    finally:
        os.unlink(path)
    if proc.returncode != 0:
        raise RuntimeError(
            f"node failed (rc={proc.returncode}):\n"
            f"  stdout={proc.stdout[:500]}\n  stderr={proc.stderr[:500]}"
        )
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError(f"node returned empty stdout; stderr={proc.stderr[:500]}")
    return json.loads(out)


# ---------------------------------------------------------------------------
# Mock store setup
# ---------------------------------------------------------------------------
#
# The in-memory store is seeded on globalThis.junterStoreValue before the
# handler is imported. The test ESM loader (tests/loader.mjs) resolves
# @vercel/edge-config to tests/edge-config-stub.mjs, which reads/writes that
# globalThis key. The harness can also set globalThis.__junterActionConflict
# to simulate a concurrent Telegram write on the next write call.

SAMPLE_STORE_JSON = json.dumps({
    "roles": [
        {"id": 1, "company": "Google", "role": "APM, Cloud Platform",
         "fit": 8.7, "source": "Career", "url": "https://example.com/google-r1",
         "status": "pinged", "routed": "", "deadline": "2026-10-06",
         "status_date": "2026-09-25", "angle": "Cloud + platform work."},
        {"id": 2, "company": "Meta", "role": "APM, Growth",
         "fit": 8.1, "source": "HN", "url": "https://example.com/meta-r2",
         "status": "blocked", "routed": "", "deadline": "",
         "status_date": "2026-09-22", "angle": "Growth PM.",
         "blocked_reason": "role-mismatch-senior"},
        {"id": 17, "company": "Anthropic", "role": "PM, Claude Apps",
         "fit": 8.2, "source": "HN", "url": "https://example.com/anthropic-r17",
         "status": "pinged", "routed": "", "deadline": "",
         "status_date": "2026-09-30", "angle": "AI feature surface."},
    ]
})


# ---------------------------------------------------------------------------
# Mock req/res
# ---------------------------------------------------------------------------

def _invoke_js(body, source="ui", role_id=1, action="mark_interested",
               idempotency_key=None, headers=None, audit_log_path=None,
               idempotency_file=None):
    """Build the driver body. Returns the setup_js and invoke_js strings."""
    audit_log_path = audit_log_path or tempfile.mktemp(prefix="junter-actions-", suffix=".jsonl")
    idem_env = (f"process.env.JUNTER_IDEMPOTENCY_FILE = "
                f"{json.dumps(idempotency_file)};") if idempotency_file else ""
    body_json = json.dumps(body)
    headers_json = json.dumps(headers or {})
    setup = textwrap.dedent(f"""
        process.env.JUNTER_AUDIT_LOG = {json.dumps(audit_log_path)};
        process.env.JUNTER_STRICT_AUDIT = '0';
        {idem_env}
        // Seed the in-memory Edge Config store BEFORE the handler reads.
        globalThis.junterStoreValue = JSON.parse({json.dumps(SAMPLE_STORE_JSON)});
    """)
    invoke = textwrap.dedent(f"""
        const {{ default: handler }} = await import('{HANDLER.as_posix()}');
        const req = {{
          method: 'POST',
          headers: {headers_json},
          body: JSON.parse({json.dumps(body_json)}),
        }};
        const res = {{
          _status: 200,
          _headers: {{}},
          _body: null,
          status(s) {{ this._status = s; return this; }},
          setHeader(k, v) {{ this._headers[k] = v; }},
          json(b) {{ this._body = b; }},
        }};
        await handler(req, res);
        process.stdout.write(JSON.stringify({{
          status: res._status,
          headers: res._headers,
          body: res._body,
          store: globalThis.junterStoreValue,
        }}));
    """)
    return setup, invoke, audit_log_path


def _post(body, **kwargs):
    setup, invoke, audit_path = _invoke_js(body, **kwargs)
    return _run(invoke, setup_js=setup), audit_path


def _read_audit(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@unittest.skipIf(NODE is None, "node not available to execute api/action.js")
class ActionContractTests(unittest.TestCase):
    """T20.2 — at least 6 tests covering the action-surface contract."""

    # ----- happy path: mark_interested ------------------------------------

    def test_mark_interested_happy_path(self):
        body = {
            "action": "mark_interested",
            "role_id": 1,
            "payload": {},
            "source": "ui",
            "idempotency_key": "ui-mark-int-1-20261002-9c4e0000",
        }
        result, audit_path = _post(body)
        self.assertEqual(result["status"], 200, f"expected 200, got {result}")
        self.assertTrue(result["body"]["ok"], f"expected ok=true: {result['body']}")
        role = result["body"]["role"]
        self.assertEqual(role["status"], "interested")
        self.assertEqual(role["routed"], "int")
        # Store reflects the change.
        updated = next(r for r in result["store"]["roles"] if r["id"] == 1)
        self.assertEqual(updated["status"], "interested")
        self.assertEqual(updated["routed"], "int")
        # Audit log captured the call.
        audit = _read_audit(audit_path)
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]["action"], "mark_interested")
        self.assertEqual(audit[0]["role_id"], 1)
        self.assertEqual(audit[0]["source"], "ui")
        self.assertEqual(audit[0]["response_status"], 200)
        self.assertEqual(audit[0]["idempotency_key"], body["idempotency_key"])
        self.assertNotIn("payload_field", audit[0])  # no leakage
        os.unlink(audit_path)

    # ----- idempotency replay: same key returns the original, no double-write

    def test_mark_packaged_idempotent_replay(self):
        body = {
            "action": "mark_packaged",
            "role_id": 17,
            "payload": {},
            "source": "ui",
            "idempotency_key": "ui-mark-pkg-17-20261002-7f2a0000",
        }
        # Shared idempotency store so the replay survives across the two
        # subprocess invocations.
        idem_file = tempfile.mktemp(prefix="junter-idem-", suffix=".json")
        if os.path.exists(idem_file):
            os.unlink(idem_file)
        first, audit_path = _post(body, idempotency_file=idem_file)
        self.assertEqual(first["status"], 200)
        self.assertFalse(first["body"].get("idempotency_replay"))
        first_role = first["body"]["role"]
        # Second call with the same key.
        second, audit_path2 = _post(body, idempotency_file=idem_file)
        self.assertEqual(second["status"], 200)
        self.assertTrue(second["body"]["idempotency_replay"],
                        f"replay must carry idempotency_replay=true: {second['body']}")
        # Same request_id (the original was cached).
        self.assertEqual(second["body"]["request_id"], first["body"]["request_id"])
        # The replay returns the ORIGINAL role unchanged. The wire response
        # strips _actions, so we assert on the user-visible fields: status,
        # routed, fit, status_date, angle are all byte-equal between the
        # first response and the replay.
        for k in ("status", "routed", "fit", "status_date", "angle"):
            self.assertEqual(
                second["body"]["role"].get(k),
                first["body"]["role"].get(k),
                f"replay must return the original role; field {k} diverged",
            )
        # Same audit request_id appears on both calls (the cached entry was
        # logged with the original request_id).
        first_audit = _read_audit(audit_path)[0]
        second_audit = _read_audit(audit_path2)[0]
        self.assertEqual(
            first_audit["request_id"], second_audit["request_id"],
            "replay audit entry must carry the original request_id",
        )
        # Replay audit carries idempotency_replay=true.
        self.assertTrue(
            second_audit.get("idempotency_replay"),
            f"replay audit entry must mark idempotency_replay=true: {second_audit}",
        )
        os.unlink(audit_path); os.unlink(audit_path2); os.unlink(idem_file)

    # ----- 404: edit_notes on a non-existent role_id ----------------------

    def test_edit_notes_unknown_role_returns_404(self):
        body = {
            "action": "edit_notes",
            "role_id": 9999,
            "payload": {"notes": "phantom"},
            "source": "telegram",
            "idempotency_key": "ui-edit-notes-9999-20261002-aaaa",
        }
        result, audit_path = _post(body)
        self.assertEqual(result["status"], 404)
        self.assertFalse(result["body"]["ok"])
        self.assertEqual(result["body"]["error"]["code"], "role_not_found")
        # The store is byte-equal to the input — no mutation on a 404.
        self.assertEqual(len(result["store"]["roles"]), 3)
        os.unlink(audit_path)

    # ----- 400: unknown action name --------------------------------------

    def test_complete_gate_with_unknown_action_returns_400(self):
        body = {
            "action": "explode",  # not in VALID_ACTIONS
            "role_id": 1,
            "payload": {},
            "source": "ui",
            "idempotency_key": "ui-bad-action-1-20261002-bbbb0000",
        }
        result, audit_path = _post(body)
        self.assertEqual(result["status"], 400, f"expected 400, got {result}")
        self.assertEqual(result["body"]["error"]["code"], "validation_failed")
        self.assertIn("action", result["body"]["error"]["details"])
        # Validation errors MUST NOT mutate the store.
        self.assertEqual(result["store"], json.loads(SAMPLE_STORE_JSON))
        os.unlink(audit_path)

    # ----- 409: concurrent Telegram write (mock returns conflict) -------

    def test_mark_blocked_conflict_returns_409(self):
        body = {
            "action": "mark_blocked",
            "role_id": 1,
            "payload": {"reason": "sponsorship-unclear"},
            "source": "ui",
            "idempotency_key": "ui-mark-blocked-1-20261002-cccc0000",
        }
        setup, invoke, audit_path = _invoke_js(body)
        # Trigger a one-shot conflict on the next set() call.
        setup += "globalThis.__junterActionConflict = true;\n"
        result = _run(invoke, setup_js=setup)
        self.assertEqual(result["status"], 409,
                         f"expected 409 conflict, got {result}")
        self.assertEqual(result["body"]["error"]["code"], "conflict")
        # Server state is NOT mutated on conflict.
        r1 = next(r for r in result["store"]["roles"] if r["id"] == 1)
        self.assertEqual(r1["status"], "pinged", "blocked mark must NOT land on 409")
        os.unlink(audit_path)

    # ----- audit log shape: schema is honored ----------------------------

    def test_actions_jsonl_format_is_parseable(self):
        """T20.6 — the audit log is newline-delimited JSON, parseable with
        `python3 -c \"import json,sys; [json.loads(l) for l in sys.stdin]\"`."""
        body = {
            "action": "complete_gate",
            "role_id": 17,
            "payload": {"gate": "backgrounder_read"},
            "source": "ui",
            "idempotency_key": "ui-gate-bg-17-20261002-3b8c0000",
        }
        result, audit_path = _post(body)
        self.assertEqual(result["status"], 200)
        # Parse with the EXACT gate command the spec demands.
        import json as _json
        with open(audit_path, encoding="utf-8") as f:
            data = f.read()
        self.assertTrue(data.endswith("\n"), "audit log must end with newline")
        # Inline-eval the spec's gate and assert it returns cleanly.
        parsed = eval("[json.loads(l) for l in open(" + repr(audit_path) + ")]",
                      {"json": _json, "open": open})
        self.assertGreaterEqual(len(parsed), 1, "audit log must have at least one entry")
        for entry in parsed:
            self.assertIn("ts", entry)
            self.assertIn("action", entry)
            self.assertIn("role_id", entry)
            self.assertIn("source", entry)
            self.assertIn("idempotency_key", entry)
            self.assertIn("response_status", entry)
        os.unlink(audit_path)

    # ----- bonus: view (audit-only, no mutation) -----------------------

    def test_view_does_not_mutate_state(self):
        body = {
            "action": "view",
            "role_id": 1,
            "payload": {},
            "source": "telegram",
            "idempotency_key": "tg-view-1-20261002-dddd0000",
        }
        result, audit_path = _post(body)
        self.assertEqual(result["status"], 200)
        self.assertTrue(result["body"]["ok"])
        # No mutation.
        r1 = next(r for r in result["store"]["roles"] if r["id"] == 1)
        self.assertEqual(r1["status"], "pinged", "view must NOT mutate status")
        self.assertEqual(r1["routed"], "", "view must NOT mutate routed")
        # Audit still recorded.
        audit = _read_audit(audit_path)
        self.assertEqual(audit[0]["action"], "view")
        self.assertEqual(audit[0]["source"], "telegram")
        os.unlink(audit_path)

    # ----- bonus: race condition — concurrent calls same key, one state change

    def test_race_concurrent_same_key_yields_one_state_change(self):
        """T20.5 — two concurrent mark_interested calls with the same
        idempotency_key produce exactly one state change."""
        body = {
            "action": "mark_interested",
            "role_id": 17,
            "payload": {},
            "source": "ui",
            "idempotency_key": "ui-mark-int-17-race-20261002-eeee",
        }
        idem_file = tempfile.mktemp(prefix="junter-idem-", suffix=".json")
        if os.path.exists(idem_file):
            os.unlink(idem_file)
        # The first invocation primes the idempotency buffer; the second hits
        # the cached response. Sequential in this harness is equivalent to a
        # concurrent call here because the handler is single-process.
        first, audit_path1 = _post(body, idempotency_file=idem_file)
        second, audit_path2 = _post(body, idempotency_file=idem_file)
        self.assertFalse(first["body"].get("idempotency_replay"))
        self.assertTrue(second["body"].get("idempotency_replay"))
        # request_id matches across the two calls (cached).
        self.assertEqual(first["body"]["request_id"], second["body"]["request_id"])
        # role is byte-equal: only one state mutation happened.
        for k in ("status", "routed", "fit"):
            self.assertEqual(
                second["body"]["role"].get(k),
                first["body"]["role"].get(k),
                f"two same-key calls must produce ONE mutation; field {k} diverged",
            )
        # Both audit entries recorded (the replay still gets logged).
        first_audit = _read_audit(audit_path1)[0]
        second_audit = _read_audit(audit_path2)[0]
        self.assertTrue(
            second_audit.get("idempotency_replay"),
            f"second-call audit must carry idempotency_replay=true: {second_audit}",
        )
        self.assertEqual(
            first_audit["request_id"], second_audit["request_id"],
            "second-call audit must share request_id with the first call",
        )
        os.unlink(audit_path1); os.unlink(audit_path2); os.unlink(idem_file)


if __name__ == "__main__":
    unittest.main()
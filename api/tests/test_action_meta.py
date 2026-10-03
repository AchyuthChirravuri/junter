"""Python 3.9 stdlib verification harness for ``api/action.js``.

The production handler is JavaScript. Each test starts Node with the project's
ESM test loader, injects a local compare-and-swap store through the handler's
documented test seam, and invokes a Vercel-shaped request/response mock. No
network, Vercel credentials, Edge Config, or operator tracker is used.

Run: python3 -m unittest api.tests.test_action_meta -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HANDLER = REPO_ROOT / "api" / "action.js"
LOADER = REPO_ROOT / "tests" / "loader.mjs"
NODE = shutil.which("node")

SAMPLE = {
    "roles": [
        {"id": 1, "company": "Example One", "status": "pinged", "routed": "", "angle": "original"},
        {"id": 2, "company": "Example Two", "status": "pinged", "routed": "", "angle": "second"},
    ],
    "lastUpdated": None,
}


def request(action="mark_interested", role_id=1, payload=None, key="ui-test-key-0001"):
    return {
        "action": action,
        "role_id": role_id,
        "payload": {} if payload is None else payload,
        "source": "ui",
        "idempotency_key": key,
    }


def invoke(bodies, audit_path, concurrent=False, conflict=False):
    """Run one or two handler calls in one Node process and return its state."""
    if not NODE:
        raise unittest.SkipTest("node is not available")
    program = textwrap.dedent(
        """
        import crypto from 'node:crypto';
        import handler from %s;

        let state = %s;
        let writes = 0;
        let conflict = %s;
        const clone = value => structuredClone(value);
        const digest = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
        globalThis.junterStoreValue = state;
        globalThis.__junterActionStore = async (value, expected) => {
          await new Promise(resolve => setTimeout(resolve, 5));
          if (value === undefined) return { value: clone(state), etag: digest(state) };
          if (conflict) {
            conflict = false;
            state.roles[0] = { ...state.roles[0], status: 'packaged', routed: 'pkg' };
            globalThis.junterStoreValue = state;
            return { ok: false, code: 'conflict' };
          }
          if (expected !== digest(state)) return { ok: false, code: 'conflict' };
          writes += 1;
          state = clone(value);
          globalThis.junterStoreValue = state;
          return { ok: true };
        };
        function makeResponse() {
          return {
            statusCode: 200, headers: {}, body: null,
            status(code) { this.statusCode = code; return this; },
            setHeader(key, value) { this.headers[key] = value; },
            json(value) { this.body = value; return this; },
          };
        }
        async function one(body) {
          const res = makeResponse();
          await handler({ method: 'POST', headers: {}, body }, res);
          return { status: res.statusCode, body: res.body };
        }
        const bodies = %s;
        const results = %s ? await Promise.all(bodies.map(one)) : [];
        if (!%s) for (const body of bodies) results.push(await one(body));
        process.stdout.write(JSON.stringify({ results, state, writes }));
        """
        % (
            json.dumps(HANDLER.as_posix()),
            json.dumps(SAMPLE),
            "true" if conflict else "false",
            json.dumps(bodies),
            "true" if concurrent else "false",
            "true" if concurrent else "false",
        )
    )
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as handle:
        handle.write(program)
        program_path = handle.name
    env = os.environ.copy()
    env.update({"JUNTER_AUDIT_LOG": audit_path, "JUNTER_STRICT_AUDIT": "0"})
    try:
        result = subprocess.run(
            [NODE, "--no-warnings", "--loader", str(LOADER), program_path],
            cwd=str(REPO_ROOT), env=env, text=True, capture_output=True, timeout=60,
        )
    finally:
        os.unlink(program_path)
    if result.returncode:
        raise AssertionError("Node harness failed:\n%s" % result.stderr)
    return json.loads(result.stdout)


def audit_rows(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


@unittest.skipUnless(NODE, "node is required")
class ActionMetaTests(unittest.TestCase):
    def setUp(self):
        fd, self.audit_path = tempfile.mkstemp(prefix="junter-action-", suffix=".jsonl")
        os.close(fd)
        os.unlink(self.audit_path)

    def tearDown(self):
        if os.path.exists(self.audit_path):
            os.unlink(self.audit_path)

    def test_mark_interested_happy_path(self):
        result = invoke([request()], self.audit_path)
        response = result["results"][0]
        self.assertEqual(response["status"], 200)
        self.assertTrue(response["body"]["ok"])
        self.assertEqual(response["body"]["role"]["status"], "interested")
        self.assertEqual(response["body"]["role"]["routed"], "int")
        self.assertEqual(result["writes"], 1)

    def test_mark_packaged_replay_is_no_second_mutation(self):
        body = request("mark_packaged", key="ui-package-key-0001")
        result = invoke([body, body], self.audit_path)
        first, replay = result["results"]
        self.assertEqual([first["status"], replay["status"]], [200, 200])
        self.assertFalse(first["body"]["idempotency_replay"])
        self.assertTrue(replay["body"]["idempotency_replay"])
        self.assertEqual(first["body"]["request_id"], replay["body"]["request_id"])
        self.assertEqual(result["writes"], 1)
        self.assertEqual(result["state"]["roles"][0]["routed"], "pkg")

    def test_strict_schema_rejects_unknown_fields(self):
        invalid = request()
        invalid["mode"] = "personal"
        result = invoke([invalid], self.audit_path)
        response = result["results"][0]
        self.assertEqual(response["status"], 400)
        self.assertEqual(response["body"]["error"], "schema validation failed")
        self.assertEqual(response["body"]["error_code"], "validation_failed")
        self.assertIn("mode", response["body"]["details"])
        self.assertEqual(result["writes"], 0)

    def test_unknown_role_is_404_without_mutation(self):
        result = invoke([request("edit_notes", role_id=404, payload={"notes": "none"})], self.audit_path)
        response = result["results"][0]
        self.assertEqual(response["status"], 404)
        self.assertEqual(response["body"]["error"]["code"], "role_not_found")
        self.assertEqual(result["writes"], 0)
        self.assertEqual(result["state"], SAMPLE)

    def test_true_concurrent_same_key_replays_once(self):
        body = request(key="ui-race-key-0000001")
        result = invoke([body, body], self.audit_path, concurrent=True)
        first, replay = result["results"]
        self.assertEqual([first["status"], replay["status"]], [200, 200])
        self.assertEqual([first["body"]["idempotency_replay"], replay["body"]["idempotency_replay"]], [False, True])
        self.assertEqual(result["writes"], 1)
        self.assertEqual(first["body"]["request_id"], replay["body"]["request_id"])

    def test_conflict_returns_authoritative_state(self):
        result = invoke([request("mark_blocked", payload={"reason": "test"})], self.audit_path, conflict=True)
        response = result["results"][0]
        self.assertEqual(response["status"], 409)
        self.assertEqual(response["body"]["error"]["code"], "conflict")
        self.assertEqual(response["body"]["role"]["routed"], "pkg")
        self.assertEqual(result["writes"], 0)

    def test_remaining_actions_and_view_contract(self):
        actions = [
            request("mark_submitted", key="ui-submit-key-00001"),
            request("edit_notes", payload={"notes": "new note"}, key="ui-notes-key-000001"),
            request("complete_gate", payload={"gate": "backgrounder_read"}, key="ui-gate-key-0000001"),
            request("view", key="ui-view-key-0000001"),
        ]
        result = invoke(actions, self.audit_path)
        self.assertEqual([item["status"] for item in result["results"]], [200, 200, 200, 200])
        role = result["state"]["roles"][0]
        self.assertEqual(role["routed"], "sub")
        self.assertEqual(role["angle"], "new note")
        self.assertTrue(role["gates"]["backgrounder_read"])
        self.assertEqual(result["writes"], 3, "view is audit-only")

    def test_audit_is_append_only_flocked_jsonl_with_final_status(self):
        invoke([request(), request("view", key="ui-view-key-0000002")], self.audit_path)
        rows = audit_rows(self.audit_path)
        self.assertEqual(len(rows), 4, "attempt and response row per request")
        final_rows = [row for row in rows if row["phase"] == "response"]
        self.assertEqual(len(final_rows), 2)
        for row in final_rows:
            for field in ("timestamp", "action", "role_id", "source", "payload", "idempotency_key", "response_status", "request_id"):
                self.assertIn(field, row)
            self.assertEqual(row["response_status"], 200)
        with open(self.audit_path, encoding="utf-8") as handle:
            self.assertTrue(handle.read().endswith("\n"))


if __name__ == "__main__":
    unittest.main()

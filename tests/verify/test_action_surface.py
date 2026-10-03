"""Contract tests exercising the real action handler through its local Node seam."""
from __future__ import annotations

import os
import tempfile
import unittest

from api.tests.test_action_meta import audit_rows, invoke, request


class ActionSurfaceVerificationTests(unittest.TestCase):
    def setUp(self):
        fd, self.audit_path = tempfile.mkstemp(prefix="verify-action-", suffix=".jsonl")
        os.close(fd)
        os.unlink(self.audit_path)

    def tearDown(self):
        if os.path.exists(self.audit_path):
            os.unlink(self.audit_path)

    def test_all_mark_actions_apply_canonical_routed_state(self):
        expected = {"mark_interested": "int", "mark_packaged": "pkg", "mark_submitted": "sub", "mark_blocked": ""}
        for number, (action, routed) in enumerate(expected.items(), 1):
            result = invoke([request(action, payload={"reason": "verification"} if action == "mark_blocked" else {}, key=f"verify-mark-{number:010d}")], self.audit_path)
            response = result["results"][0]
            self.assertEqual(response["status"], 200, f"api/action.js: {action} should return 200")
            self.assertEqual(response["body"]["role"]["routed"], routed, f"api/action.js: {action} wrote wrong routed state")

    def test_edit_notes_and_complete_gate_preserve_schema(self):
        bodies = [request("edit_notes", payload={"notes": "Synthetic verification note"}, key="verify-notes-00001"), request("complete_gate", payload={"gate": "backgrounder_read"}, key="verify-gate-000001")]
        result = invoke(bodies, self.audit_path)
        self.assertEqual([r["status"] for r in result["results"]], [200, 200], "api/action.js: edit_notes and complete_gate must succeed")
        role = result["state"]["roles"][0]
        self.assertEqual(role["angle"], "Synthetic verification note", "api/action.js: edit_notes did not persist the supplied note")
        self.assertTrue(role["gates"]["backgrounder_read"], "api/action.js: complete_gate did not persist the gate")

    def test_idempotency_replays_without_second_mutation(self):
        body = request("mark_interested", key="verify-idempotent1")
        result = invoke([body, body], self.audit_path)
        first, replay = result["results"]
        self.assertEqual(result["writes"], 1, "api/action.js: duplicate key caused more than one mutation")
        self.assertFalse(first["body"]["idempotency_replay"])
        self.assertTrue(replay["body"]["idempotency_replay"])
        self.assertEqual(first["body"]["request_id"], replay["body"]["request_id"])

    def test_schema_and_missing_role_error_paths_are_safe(self):
        invalid = request(key="verify-invalid0001")
        invalid["unexpected"] = True
        missing = request("edit_notes", role_id=9999, payload={"notes": "x"}, key="verify-missing0001")
        result = invoke([invalid, missing], self.audit_path)
        self.assertEqual([r["status"] for r in result["results"]], [400, 404])
        self.assertEqual(result["results"][0]["body"]["error_code"], "validation_failed")
        self.assertEqual(result["results"][1]["body"]["error"]["code"], "role_not_found")
        self.assertEqual(result["writes"], 0, "api/action.js: rejected requests must not mutate state")

    def test_audit_records_every_attempt_and_response(self):
        invoke([request(key="verify-audit000001")], self.audit_path)
        rows = audit_rows(self.audit_path)
        self.assertEqual([row["phase"] for row in rows], ["attempt", "response"], "lib/audit-append.py: audit rows must be append-only attempt/response pairs")
        self.assertEqual(rows[-1]["response_status"], 200)


if __name__ == "__main__":
    unittest.main()

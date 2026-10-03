"""Local mock/DOM acceptance, not deployed browser evidence. Stdlib only."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

NODE = shutil.which('node')
HARNESS = Path(__file__).with_name('action_client_harness.cjs')

@unittest.skipIf(NODE is None, 'Node is required for real client execution')
class OptimisticActionTests(unittest.TestCase):
    def check(self, name):
        assert NODE is not None
        result = subprocess.run([NODE, str(HARNESS), name], capture_output=True,
                                text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertTrue(json.loads(result.stdout)['ok'])

    def test_immediate_visual_update_and_authoritative_success(self): self.check('visual_success')
    def test_validation_server_and_other_http_failures(self): self.check('failures')
    def test_network_failure_and_same_body_retry_button(self): self.check('network_retry')
    def test_double_click_deduplicates_inflight_action(self): self.check('duplicate')
    def test_different_roles_rollback_isolated(self): self.check('different_roles')
    def test_same_role_queue_preserves_newer_actions(self): self.check('same_role_queue')
    def test_conflict_reconciles_authoritative_state(self): self.check('conflict')
    def test_supported_controls_notes_and_gates(self): self.check('supported_controls')
    def test_sandbox_only_uuid_and_no_credentials(self): self.check('sandbox_uuid')
    def test_unsafe_action_response_rejected(self): self.check('unsafe_response')
    def test_all_supported_actions_and_nested_notes_rollback(self): self.check('all_supported_actions')
    def test_offline_sample_is_read_only_without_identifier_guessing(self): self.check('offline_sample')
    def test_expired_retry_requires_reload(self): self.check('expired_retry')
    def test_superseded_retry_cannot_overwrite_newer_action(self): self.check('superseded_retry')

if __name__ == '__main__':
    unittest.main()

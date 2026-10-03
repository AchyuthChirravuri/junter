# Junter pre-deploy checklist

Run `bash tests/verify/run_all.sh` from the repository root before an authorized deployment. A local PASS is not deployed acceptance: it must continue to report `LIVE_ACCEPTANCE=PENDING` until the exact newly deployed commit is probed.

- [ ] 1. Approved export still contains all 11 canonical Figma frames → `tests/verify/test_figma_parity.py::FigmaParityTests.test_export_has_exactly_eleven_canonical_frames`
- [ ] 2. Figma section names and documented screen anchors match the HTML render source → `tests/verify/test_figma_parity.py`
- [ ] 3. Figma color inventory and CSS palette are identical → `tests/verify/test_figma_parity.py::FigmaParityTests.test_color_token_inventory_matches_css_exactly`
- [ ] 4. Every CSS custom property equals the documented token contract → `tests/verify/test_design_tokens.py::DesignTokenTests.test_every_css_variable_has_the_documented_value`
- [ ] 5. CSS contains no orphan hexadecimal color literals → `tests/verify/test_design_tokens.py::DesignTokenTests.test_css_has_no_orphan_hex_codes`
- [ ] 6. Every deployable synthetic JSON payload passes the PII guard → `tests/verify/test_pii_guard.py::PiiGuardTests.test_all_committed_json_payloads_are_safe`
- [ ] 7. No real tracker fixture is committed to the public repository → `tests/verify/test_pii_guard.py::PiiGuardTests.test_real_tracker_sample_is_not_committed`
- [ ] 8. All six action types mutate their expected state locally → `tests/verify/test_action_surface.py::ActionSurfaceVerificationTests.test_all_mark_actions_apply_canonical_routed_state`
- [ ] 9. Actions are idempotent and error paths do not mutate state → `tests/verify/test_action_surface.py`
- [ ] 10. All five product mechanism strengths have named, visible UI surfaces → `tests/verify/test_strong_surface.py`
- [ ] 11. Every current canonical screenshot is within 5% of its approved golden snapshot → `tests/verify/test_visual_regression.py`
- [ ] 12. After an authorized deployment only, exact-SHA live status/content-type/marker probes pass → `LIVE_URL=https://new-deployment INTENDED_SOURCE_SHA=<sha> LIVE_SOURCE_SHA=<sha> bash tests/verify/run_all.sh live`

The committed `docs/ui-evidence/current/` images are the approved T18 Figma baseline used for the offline snapshot integrity gate. T22 must replace them with newly captured HTML screenshots for the deployment-specific visual check; an old deployment can never be accepted as evidence for a new SHA.

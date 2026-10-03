# Telegram shared-action integration — local evidence and activation blocker

Task: t_d4cde654. Status: LOCAL_MOCK_IMPLEMENTATION verified; gateway activation BLOCKED; live acceptance PENDING. No deployment, push, commit, real HTTP write, CSV mutation, profile change, or gateway restart performed.

## Discovery and scope

The existing jobs-profile `skills/job-intent/SKILL.md:14-29` routes `int` operations to `job-applications/junter-overnight/job_intent_handler.py:139-247`. That implementation writes the local CSV. There was no shared-endpoint client in that path. The generic Telegram gateway is not itself a job-specific parser.

The new deterministic plugin handles authorized role commands at the host's `pre_gateway_dispatch` hook, before an LLM turn can follow those old CSV instructions. It invokes the host authorization method first because the hook is pre-auth (`gateway/run_inbound.py:270-275`). Recognized authorized commands always return `skip`, including configuration, parse, transport, and reply-delivery failures. Unrelated messages, other platforms, internal events, and unauthorized pairing workflows remain under core handling. Bot role actions fail closed.

IMPORTANT: the plugin has NOT been installed/enabled in the running jobs profile. Consequently the current live `int` path still uses the old CSV writer. This card must not be called complete or describe the running gateway as migrated. Existing skills, the CSV handler, discovery jobs, and the live gateway were left unchanged.

## New source

- `integrations/telegram_actions.py`: stdlib command parser, private persistent receipt journal, HTTP transport, safe feedback, gateway hook.
- `integrations/hermes-plugin/plugin.yaml` and `__init__.py`: jobs-only native plugin manifest/registration. Resolve the module relative to the source symlink, not a private endpoint in code.
- `integrations/tests/test_telegram_actions.py`: 21 mock-only command/client/hook tests.
- `integrations/tests/test_telegram_shared_endpoint.py`: actual JS handler/store-mock round trip and plugin registration tests.

Supported commands: `int 3 5 7`, `pkg <IDs>`, `sub <IDs>`, `blocked <IDs>`, `view <IDs>`, `notes <ID> <text>`, `gate <ID> <supported gate>`. Full contract action names are accepted as equivalent names. Bracket/comma integer lists remain supported; duplicate IDs within a batch send once. Entire batches are validated before sending. No unrelated commands or workflow semantics were invented.

Each role operation POSTs `{action,role_id,payload,source:"telegram",idempotency_key}` to the configured HTTPS `/api/action`. Keys are distinct UUIDs persisted before HTTP. Retries use exactly the same body/key. The private SQLite journal is mode 0600 and serializes concurrent deliveries with flock; it retains metadata and safe state summaries, not note text, endpoint/token values, or raw server errors. Completed message replays do not POST again. Edited messages cannot reuse old keys or append unjournaled operations. An uncertain operation cannot retry after 55 seconds; the operator must inspect authoritative state before issuing a fresh command. This bounds retries inside the 60-second contract window rather than manufacturing a new key for an uncertain write.

The HTTP transport denies redirects and uses a private bearer token. Successful acknowledgments require `ok=true`, a matching authoritative role ID, request_id, and applied_at. Validation, role-not-found, conflict, authorization, rate-limit, network/protocol, and server failures produce fixed safe feedback. 409 reports the authoritative state when available and does not auto-overwrite it. A success/replay never claims the local CSV or CSV-based backgrounder queue was updated.

Server idempotency remains process-local in the sibling API implementation. Client UUID retention is verified; cross-instance/cold-start server duplicate suppression is NOT established and must not be claimed.

## Evidence

From the repository:

    python3 -m unittest integrations.tests.test_telegram_actions integrations.tests.test_telegram_shared_endpoint -v

Result: 23 tests, all PASS, 0 skipped, 0.711 seconds. Python 3.9.6 stdlib; Node executes the actual JS handler. The shared-endpoint test generated bodies for `int 3 5 7`, then replayed the first key against one handler instance: four HTTP-shaped 200 responses, exactly three mocked store writes, the fourth response `idempotency_replay=true`, and four final audit records with `source=telegram`. Mock fetch throws if network is attempted; audit/receipts reside in a temporary fixture directory.

The combined command run by `verify_telegram_local.py` included those 23 plus the existing UI ActionSurfaceClientTests and PiiGuardRuntimeTests: 28 ran, 25 passed, 3 UI tests failed with `offline_sample`. Exact output: assigned workspace `telegram-local-tests.txt`. The UI task received these failures; its files are a sibling hotspot and were not edited here. This is NOT an all-green integrated T20 pass. The real tracker SHA-256 was identical before and after the combined run; its contents/digest were not copied into the report.

## Activation and missing private configuration

The presence-only check found all three new private process settings absent: `JUNTER_TELEGRAM_ACTIONS_ENABLED`, `JUNTER_ACTION_ENDPOINT`, `JUNTER_ACTION_TOKEN`. No values were printed, stored here, or fetched from a credential provider.

After an approved functional protected endpoint exists, the operator must provide its private `/api/action` HTTPS URL/token, install the source plugin as a symlink in the jobs profile's plugins directory, and enable `junter-actions` through the supported Hermes plugin command. A controlled gateway reload is needed; no running process was restarted here. The enable flag must be explicitly `1` before live transport is allowed. Settings/credentials stay in the private process/profile mechanism, never in this repository. Re-run mock tests and verify profile/plugin discovery before activating. This is an activation procedure, not evidence that activation occurred.

API sibling t_a4a9f7f8 is blocked: the current handler rejects Vercel writes with 503 because durable flocked audit is unavailable, and the production store refuses writes without atomic concurrency protection. Do not route live Telegram commands to it as though it supports production writes. The operator must resolve that host/storage contract first. No endpoint was guessed or substituted with the public demo.

## Publisher and CSV-sync boundary

The intended flow is:

    operator-enabled CSV publisher -> protected Edge Config
    UI and Telegram -> POST /api/action -> same authoritative store
    separately invoked operator sync -> local CSV

Neither this client/plugin nor the UI action handler invokes the publisher or a sync, imports tracker mutation helpers, or schedules automatic CSV updates. The publisher is an operator-enabled outbound snapshot mechanism, not a second Telegram action route. Publishing an older CSV can overwrite newer endpoint changes unless reconciled; operators must inspect/reconcile differences rather than blindly republish.

T17 specifies publishing disabled by default and an explicit publishing opt-in. The current `snapshot-export/export.py:597-610` exposes export/output arguments, not the spec's `--publish --target` flags. No implemented Edge-Config-to-CSV sync command was located in the inspected project. Therefore those flags/commands are not claimed as working, were not invented, and were not added in this task. Their implementation/activation is a separate workstream. CSV-consuming backgrounder automation cannot be said to pick up these endpoint actions until a separately authorized sync exists and is invoked.

## Required handoff

QA t_96813bb2 can rerun the isolated tests immediately but must not mark the existing live gateway migrated or local T20 fully passing. Activation requires operator private configuration plus resolution of the API persistence/host blocker. Deployed acceptance remains t_7bcccf7e after separately authorized protected deployment. No production behavior is inferred from mocks.

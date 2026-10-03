# T20 integrated local acceptance report

Status: LOCAL MOCK ACCEPTANCE PASSED for the verified handler, client, and Telegram adapter paths. This is not deployment acceptance, production-persistence acceptance, or proof of a live browser round trip.

Run date: 2026-10-03 10:34 EDT
Integration owner: t_96813bb2
Deployed browser acceptance owner: t_7bcccf7e (PENDING; separately authorized protected deployment required)

## Scope and safety

This pass exercised `api/action.js` through Vercel-shaped request/response mocks and an explicitly injected in-memory compare-and-swap store. It did not access credentials, deploy, call a real endpoint, modify Vercel or Edge Config, alter the operator's CSV, install dependencies, push, or commit.

The real tracker SHA-256 before and after the pass was identical:

    2780a2cd7461853a416aac6ec78c99167ac1626b89d0f5622748fc513a5ad9c5

`git diff --check` passed. A bounded JavaScript source scan for hard-coded secret-like assignments returned no matches.

## Reproducible local evidence

Run these commands from the repository root:

    python3 -m unittest api.tests.test_action_meta -v
    node --no-warnings --loader ./tests/loader.mjs --test tests/api/action-repair.mjs
    python3 -m unittest ui.tests.test_optimistic_actions ui.tests.test_app -v
    python3 -m unittest integrations.tests.test_telegram_actions integrations.tests.test_telegram_shared_endpoint -v
    git diff --check

Results from this pass:

- `api.tests.test_action_meta`: 8 passed. This Python 3.9-standard-library harness invokes the actual JavaScript handler using the supported ESM loader, mocked Vercel request/response objects, a local atomic adapter, and temporary audit files.
- `tests/api/action-repair.mjs`: 12 passed. It verifies strict validation, all status transitions, notes and gates, audit-only `view`, unknown-role handling, true `Promise.all` same-key replay, 60-second expiry behavior, authoritative 409 behavior, server-owned mode selection, mocked Edge Config PATCH/read consistency, final audit fields, multi-process OS-flocked audit appends, and fail-closed Vercel/storage behavior.
- Client suites: 84 passed, 1 pre-existing design-token test skipped because `docs/design-tokens.md` is absent. The new optimistic-action checks cover immediate optimistic movement, success reconciliation, isolated rollback, toast/retry behavior, 409 authoritative reconciliation, same-role queueing, UUID replay, and action controls.
- Telegram suites: 23 passed. They cover shared-endpoint request routing, independent persisted UUIDs, duplicate/retry safety, error handling, authorization boundaries, mocked API interaction, and no CSV mutation.
- `git diff --check`: passed.

## T20 local gate ledger

| Gate / requirement | Local result | Evidence |
| --- | --- | --- |
| POST handler, strict request shape, documented action response behavior | PASS with mocks | 8 Python harness tests; 12 Node handler tests |
| `mark_interested` success | PASS with mock store | `test_mark_interested_happy_path` |
| `mark_packaged` and 60-second idempotency replay without second mutation | PASS within one handler process | `test_mark_packaged_replay_is_no_second_mutation` |
| strict schema rejection | PASS | `test_strict_schema_rejects_unknown_fields` |
| unknown role returns 404 | PASS | `test_unknown_role_is_404_without_mutation` |
| true concurrent same-key calls make one mutation | PASS within one handler process | `test_true_concurrent_same_key_replays_once`; Node `Promise.all` test |
| concurrent write returns 409 with authoritative state | PASS with mock CAS conflict | `test_conflict_returns_authoritative_state` |
| remaining supported actions | PASS: submitted, notes, gate, view | `test_remaining_actions_and_view_contract`; Node transitions test covers all mark actions |
| audit required fields, JSONL append format, OS locking | PASS locally | `test_audit_is_append_only_flocked_jsonl_with_final_status`; Node 12-writer flock test |
| sandbox isolation and server-owned mode | PASS locally | Node sandbox/personal selection test |
| Edge Config update/read consistency | PASS only through mocked REST PATCH and mocked GET | Node REST/read test |
| client optimistic success, rollback/toast, conflict handling | PASS with mocked DOM/fetch | 84-client-test run |
| Telegram shared-endpoint routing | PASS with mocks | 23 Telegram tests |
| no real tracker modification | PASS | identical tracker SHA-256 before/after |

## Changed file in this integration pass

- `api/tests/test_action_meta.py`: replaced the stale subprocess fixture with a Python-stdlib harness for the current handler seam. The previous version expected a removed cross-process idempotency JSON file, an old Edge Config SDK write path, a nested validation-error shape, and one audit record per request. The replacement has 8 passing tests, including a genuine same-process concurrent request test rather than two sequential processes.

Sibling implementation files are present but intentionally not attributed to this integration change: `api/action.js`, `lib/store.js`, `lib/audit-append.py`, client files, Telegram integration files, and their supporting tests/docs.

## Requirements that cannot be established locally

The full local specification was recovered from `docs/refactor-spec-2026-10-03.md` §3 and the parent T20 card. The following cannot be honestly marked verified by a local mock:

1. Real Vercel Edge Config mutation/read propagation and the stated cache window. The mock proves request shape and in-memory consistency only. Existing GET cache headers are `s-maxage=60, stale-while-revalidate=300`; this is not a read-your-write guarantee.
2. Production atomic compare-and-swap. The available Vercel REST PATCH API has no verified atomic precondition, so `writeStore` intentionally fails closed without a mocked adapter. Cross-instance/cold-start idempotency and rate limits are likewise not established.
3. Durable production audit. The local audit uses `fcntl.flock`, `O_APPEND`, and `fsync`; Vercel Functions have no verified shared durable writable file path or portable Python/flock support. The handler returns 503 under `VERCEL` before mutation rather than claiming an unlocked `/tmp` audit is durable.
4. The protected personal deployment's authentication boundary, including protection of GET `/api/data`.
5. Browser/deployed action flow: click -> POST -> next deployed GET showing `routed="int"`. This is transferred to t_7bcccf7e after protected deployment is separately authorized.
6. Telegram gateway activation. The plugin/source is mock-tested but not installed or enabled in the running jobs profile; the existing live CSV writer was not altered.
7. Structural public-read-only requirement in T17 §2.2. The local handler currently accepts sandbox-mode writes for test/demo paths, while the T17 public URL contract says `can_write: false` and no public write endpoint. The actual public/private Vercel project split and route exposure must be established before a deployment can claim compliance.
8. An operator-approved Edge-Config-to-CSV reconciliation mechanism. No automatic or live CSV synchronization was run or claimed.

## Integration blockers and next owner

Production storage architecture is blocked pending a durable, shared audit destination and a genuine atomic single-writer/CAS design that coordinates UI, Telegram, and the CSV publisher. Do not bypass this with a process mutex, a local mock, or an unguarded read-then-PATCH operation.

Private Telegram activation is blocked pending a protected functional endpoint plus operator-owned configuration and explicitly authorized plugin installation/enablement. No endpoint/token was retrieved or recorded here.

Deployed browser acceptance remains PENDING with t_7bcccf7e. It must run only after t_1faf87ba's protected deployment prerequisite and must report actual browser/network evidence rather than extrapolating from this local report.

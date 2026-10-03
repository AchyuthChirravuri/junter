# Action API contract and persistence repair

Status: LOCAL MOCK IMPLEMENTATION VERIFIED; PRODUCTION PERSISTENCE BLOCKED.
No deployment, real Edge Config operation, CSV mutation, push, credential lookup, or new dependency install was performed. Existing commits 4878638 and 3659e59 remain intact. api/data.js is unchanged.

## Request

POST /api/action accepts only action, role_id, payload, source, idempotency_key, and optional client_ts. The action, role_id, source and key are required. role_id must be a positive safe integer, not a numeric string. source is ui or telegram. Keys follow T17: 16–64 ASCII letters/digits/underscores/hyphens (UUIDs work). A nonempty key alone is not enough under the upstream strict schema. client_ts, when supplied, must be a timestamp with timezone.

Example:

    {"action":"mark_interested","role_id":1,"payload":{},"source":"ui","idempotency_key":"mock-action-key-00000001"}

Payload omitted means {}. Supplied null, arrays or scalars are rejected. Payload shapes:

- mark_interested, mark_packaged, mark_submitted, view: {} only.
- mark_blocked: {} or {reason: nonempty string}; default reason user-marked.
- edit_notes: {notes: string}; empty string clears the note. Both angle and existing company_research.application_strategy.angle change.
- complete_gate: {gate: backgrounder_read | resume_drafted | cover_letter_drafted | references_notified | submission_logged}.

No mode, store identifier, client-supplied version, arbitrary payload property or extra action is accepted. T17 does not define a request version/CAS field; client_ts is metadata, NOT a version precondition. Do not invent one in either client without updating the contract.

## Responses

Every action response includes ok, role (null when unavailable), idempotency_replay, request_id and applied_at. Successful responses use 200 and updated role. Internal _actions is excluded from role. Actions return Cache-Control: no-store.

Validation returns HTTP 400 with the explicitly requested top-level shape:

    {"ok":false,"role":null,"idempotency_replay":false,"error":"schema validation failed","details":{"role_id":"positive integer required"},"error_code":"validation_failed","request_id":"…","applied_at":"…"}

This intentionally corrects the older implementation's nested error.details. Consumers should use error_code for this case; other failures preserve T17's error object {code,message}. Unknown roles return 404 / role_not_found. Invalid auth returns 401 / unauthorized. GET returns 405 + Allow: POST. Process-local rate limiting returns 429 + Retry-After: 60 (10 validated attempts/minute/IP or operator bucket). Successful replays bypass rate limiting.

A write adapter must atomically compare the read etag and commit, or return {ok:false,code:'conflict'}. On conflict, the handler re-reads the adapter and returns 409 with role equal to the authoritative role, so the client replaces optimistic state rather than keeping the rejected mutation. Successful writes are also read back before reporting success. Unexpected persistence/read/audit failure returns 503 with a generic non-secret error. A different role ID representation such as r01 must be mapped to the integer ID by the client/seed owner; the API does not normalize arbitrary identifiers.

## Transitions and replay

mark_interested -> interested/int; mark_packaged -> packaged/pkg; mark_submitted -> submitted/sub; mark_blocked -> blocked/empty routed. Status transitions update status_date and clear old blocked_reason unless blocking. complete_gate adds a true gate; it never toggles off. view is truly audit-only: no history mutation, no Edge Config write, no lastUpdated change.

Process-local Promise serialization occurs before asynchronous storage reads. Thus two genuinely concurrent requests with one key cannot both mutate in a single process. Keys are scoped by server mode and config ID, and expire after 60 seconds measured from success; later use is a fresh action. Same key within the window returns the original response (original request_id/applied_at/role), regardless of changed payload. Only successful responses enter the cache; rejected operations may retry.

Limitations: cache and rate limits reset on process restart, are not shared across instances, and are not persisted. The prior unlocked JUNTER_IDEMPOTENCY_FILE path was removed rather than advertised as shared durable storage. Cold-start/cross-instance duplicate suppression is NOT established. Replayed roles may be older than subsequent actions. Audit success and Edge Config commit are not one transaction: if final logging fails after a write, the pending audit record remains, a 503 is returned, and a committed action may already exist. A durable transactional outbox is needed for stronger semantics.

## Modes, credentials and stores

Mode is server-owned: JUNTER_MODE=sandbox by default, or personal on a separately configured private deployment. The body cannot change modes. Sandbox uses JUNTER_SANDBOX_CONFIG_ID; personal uses JUNTER_PERSONAL_CONFIG_ID. Identical configured sandbox/personal IDs are rejected. EDGE_CONFIG must identify the selected config, because GET /api/data independently reads that connection. The same junter-data item is used in each separate store, never a public real-data item.

Personal actions require configured JUNTER_BEARER_TOKEN plus matching Authorization: Bearer or x-junter-token; missing configuration does not authorize personal writes. A sandbox token is not an authorization path to personal data. JUNTER_VERCEL_API_TOKEN and optional JUNTER_VERCEL_TEAM_ID are server-only REST credentials and must never appear in client assets or committed values. No credentials were fetched. Local tests use an explicit server-side mock adapter, not an automatic in-memory fallback in production.

Important remaining privacy dependency: existing GET /api/data has no authentication or mode guard. This task was prohibited from editing it. A personal deployment must protect that endpoint at the deployment boundary before receiving private data. This API alone cannot establish deployment-wide privacy.

## Edge Config path and unresolved concurrency

The original adapter imported nonexistent SDK set and ignored expectedEtag. Corrected: SDK get is read-only; writes use a Vercel management REST PATCH payload:

    PATCH https://api.vercel.com/v1/global-config/<config-id>/items
    {"items":[{"operation":"upsert","key":"junter-data","value":<snapshot>}]}

The current provider OpenAPI calls the former Edge Config Global Config. Source: https://openapi.vercel.sh, operation patchEdgeConfigItems, request schema items/operation/key/value. The exported patchEdgeConfig helper is exercised with a mock fetcher, and 409/412 responses map to conflict. The helper is NOT a CAS implementation.

BLOCKER: the retrieved PATCH OpenAPI documents no expected digest/version/If-Match request precondition. Read-then-check then PATCH is not atomic and can lose concurrent writes. Production writeStore therefore returns concurrency_unavailable and does NOT invoke an unguarded REST update. Enabling full production writes requires a supported atomic precondition or a durable single-writer/transactional system coordinating UI, Telegram and the CSV publisher. A process mutex, digest reread, or undocumented header is not a substitute. Local mocks provide a real atomic adapter for acceptance, but do not prove remote support.

## Data cache

Mutations replace the roles array, mirror an existing pipeline array, and update lastUpdated, preserving sibling sections. GET /api/data returns this same junter-data item. Mock test verifies POST -> adapter -> mocked REST -> GET result. Its existing cache policy remains s-maxage=60, stale-while-revalidate=300. Contrary to the old promise, this does NOT guarantee read-your-write within 60 seconds: stale content can be served while revalidation runs, and store propagation adds further delay. Clients should adopt the returned authoritative role immediately; deployment freshness needs a separately approved cache/invalidation change. No cache change was made here.

## Append-only audit

Local default path is api/actions.jsonl. JUNTER_AUDIT_LOG may override it for isolated local testing only. lib/audit-append.py uses Python standard library fcntl.flock(LOCK_EX), O_APPEND, complete-record writes under the same inode lock, and fsync before close. Files are created mode 0600. All cooperating writers must use the same lock protocol. Existing files are not truncated or chmodded. Logs must not be committed or served publicly; they may contain private notes.

Every normal attempt generates two JSONL records: phase=attempt before mutation (response_status:null), and phase=response after resolution (actual HTTP status). Both contain timestamp, action, role_id, source, payload, idempotency_key, response_status and request_id; absent/malformed fields are null. ts aliases timestamp for older consumers. Replays still generate an attempt and final record with idempotency_replay:true. Filter phase=response when counting responses; two records are not two mutations.

BLOCKER: Vercel Functions have a read-only deployment filesystem and writable ephemeral /tmp scratch, not a durable shared api/actions.jsonl. Source: https://vercel.com/docs/functions/runtimes (filesystem support); https://github.com/vercel/community/discussions/314 (temporary vs persistent storage). Node itself supplies no portable flock and availability of the local Python helper is not established in Vercel's Node deployment. Accordingly VERCEL runtime rejects actions with 503 before any mutation; it never silently switches to /tmp, unlocked appends, or ignored audit failures. Such rejected attempts cannot be durably logged on that unsupported runtime. Meeting the original requirement needs a durable flock-capable host/path or an explicitly approved audit-store contract change. No runtime experiment or deployment was attempted.

## Verification and downstream integration

Node v24.15.0 / Python 3.9.6, local command:

    node --no-warnings --loader ./tests/loader.mjs --test tests/api/action-repair.mjs

12 tests passed: strict schema, all mutations, audit-only view, unknown role, real Promise.all race, expiration, authoritative conflict, mode isolation/auth, mocked REST plus GET consistency, all audit fields, 12 concurrent OS-locked appends, fail-closed runtime/storage.

Legacy api/tests/test_action_meta.py was intentionally left for the integrated QA owner. The rerun failed 7 tests with 1 error: its mock only seeds the old SDK get/set stub, assumes removed cross-process idempotency JSON, asserts nested 400 errors, and counts one audit record. It must inject __junterActionStore(value,expectedEtag,context), use same-process concurrent requests and phase=response records, and assert top-level validation details. The separate new suite shows the supported path but is not a claim that the legacy acceptance suite passes.

npm test also failed due to absent installed @vercel/edge-config. A loader-wide rerun is not a solution: the legacy route tests register their own SDK stub and conflict with the loader stub, producing five route-test failures. No dependency was installed or existing unrelated test edited. Run the targeted action command above; integrated QA owns the unified harness.

LIVE_ACCEPTANCE remains PENDING in t_7bcccf7e after protected deployment authorization. Runtime audit, distributed CAS, cache freshness and personal GET protection must be resolved first. This API task cannot be called production-complete.

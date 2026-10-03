# Synthetic transactional storage contract

Purpose: Junter's public synthetic demo reads only the Neon Postgres namespace `junter_synthetic`. It must never read, copy, or modify the pre-existing shared Edge Config or tracker data. The production demo is read-only: `/api/action` returns `403 public_demo_read_only` before it opens a store transaction.

## Configuration

Server-only environment keys:

- `JUNTER_SYNTHETIC_DATABASE_DATABASE_URL` — integration-managed Neon connection URL. Never expose it to the client, logs, source, or task artifacts.
- `JUNTER_SYNTHETIC_DATABASE_NAMESPACE` — optional identifier; defaults to `junter_synthetic` and accepts only lowercase letters, digits, and underscores.
- `JUNTER_SYNTHETIC_WRITES_ENABLED` — protected Preview deployment only; must be exactly `true` before a synthetic action can run.
- `JUNTER_SYNTHETIC_WRITE_TOKEN` — protected Preview deployment only; server-side shared authorization secret accepted in an HTTP header. It is never placed in UI code, a URL, or a client bundle.

The database keys may be set in `preview` and `production` only. The two write keys may be set only in a protected Preview deployment, never in production, development, or any other/unset deployment environment. Production remains read-only even if those write keys are mistakenly present. Do not alter `EDGE_CONFIG` or deploy before validating the database and seed.

## Schema and seed

`storage/migrations/001_synthetic_transactional_store.sql` creates three tables in the synthetic-only namespace:

1. `roles`: canonical role JSON, keyed by integer role id.
2. `idempotency`: one persistent key/fingerprint/result per accepted request.
3. `audit_events`: one durable record for each accepted action.

`scripts/seed-synthetic.mjs` accepts only `synthetic-data/seed.json` with `snapshot_kind: "synthetic"`; it inserts roles with `ON CONFLICT DO NOTHING`. It does not read any tracker file. Run it only through a secure server-side environment where the connection URL is already supplied; do not create or save a `.env` file.

## Transaction semantics

In the protected Preview deployment path only, each permitted fixed-shape POST opens one database transaction, locks the idempotency row and target role, mutates the role, records the idempotency result, and appends the audit event before commit. The idempotency insert deliberately precedes the audit insert: concurrent first uses collide at the durable idempotency record, roll back the losing transaction, and replay the winner response. An audit failure rolls back the state and idempotency writes with the same transaction. Repeating the same key and payload returns the persisted result; repeating the key with a different payload returns HTTP 409. GET reads the same `roles` table and has `Cache-Control: no-store`.

Free-form `edit_notes` is unavailable in synthetic storage, and `mark_blocked` rejects caller-supplied `reason`. The remaining test actions use only fixed action names and server-owned synthetic state, so neither unauthenticated callers nor authorized preview checks can persist arbitrary text into the demo dataset.

A missing/invalid database configuration returns a safe 503 response. There is no fallback to filesystem locks, process-local state, the UI fixture, or Edge Config for the public routes.

## Required remote validation before deployment

1. Use the restricted Neon integration identity for this namespace only; do not grant or use legacy tracker/Edge Config credentials.
2. Run the migration/seed command once through a secret-managed execution context, then read the role count and confirm it equals the approved synthetic fixture count.
3. Exercise two independent database clients with the same and conflicting idempotency keys; verify one mutation/audit event and durable replay after reconnect.
4. Confirm the database keys exist in preview and production without displaying values, and confirm write keys are absent from production. Any action verification uses a protected Preview path; deployment and live browser action verification remain separate gates.

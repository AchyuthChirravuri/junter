# Synthetic transactional storage contract

Purpose: Junter's public synthetic demo reads and mutates only the Neon Postgres namespace `junter_synthetic`. It must never read, copy, or modify the pre-existing shared Edge Config or tracker data.

## Configuration

Server-only environment keys:

- `JUNTER_SYNTHETIC_DATABASE_DATABASE_URL` — integration-managed Neon connection URL. Never expose it to the client, logs, source, or task artifacts.
- `JUNTER_SYNTHETIC_DATABASE_NAMESPACE` — optional identifier; defaults to `junter_synthetic` and accepts only lowercase letters, digits, and underscores.

The deployment/configuration task may set these keys in `preview` and `production` only. It must not add them to `development`, alter `EDGE_CONFIG`, or deploy before validating the database and seed.

## Schema and seed

`storage/migrations/001_synthetic_transactional_store.sql` creates three tables in the synthetic-only namespace:

1. `roles`: canonical role JSON, keyed by integer role id.
2. `idempotency`: one persistent key/fingerprint/result per accepted request.
3. `audit_events`: one durable record for each accepted action.

`scripts/seed-synthetic.mjs` accepts only `synthetic-data/seed.json` with `snapshot_kind: "synthetic"`; it inserts roles with `ON CONFLICT DO NOTHING`. It does not read any tracker file. Run it only through a secure server-side environment where the connection URL is already supplied; do not create or save a `.env` file.

## Transaction semantics

For each POST, the adapter opens one database transaction, locks the idempotency row and target role, mutates the role, records the idempotency result, and appends the audit event before commit. Repeating the same key and payload returns the persisted result; repeating the key with a different payload returns HTTP 409. GET reads the same `roles` table and has `Cache-Control: no-store`.

A missing/invalid database configuration returns a safe 503 response. There is no fallback to filesystem locks, process-local state, the UI fixture, or Edge Config for the public routes.

## Required remote validation before deployment

1. Use the restricted Neon integration identity for this namespace only; do not grant or use legacy tracker/Edge Config credentials.
2. Run the migration/seed command once through a secret-managed execution context, then read the role count and confirm it equals the approved synthetic fixture count.
3. Exercise two independent database clients with the same and conflicting idempotency keys; verify one mutation/audit event and durable replay after reconnect.
4. Confirm the Vercel keys exist in preview and production without displaying values. Deployment and live browser action verification remain separate gates.

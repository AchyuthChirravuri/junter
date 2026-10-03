-- Synthetic-only Junter transactional namespace.
-- Apply with the integration-managed database URL; never against the legacy
-- tracker or Edge Config. This migration contains no data and no credentials.
CREATE SCHEMA IF NOT EXISTS junter_synthetic;

CREATE TABLE IF NOT EXISTS junter_synthetic.roles (
  role_id integer PRIMARY KEY,
  payload jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS junter_synthetic.idempotency (
  idempotency_key text PRIMARY KEY,
  fingerprint text NOT NULL,
  response jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS junter_synthetic.audit_events (
  audit_id bigserial PRIMARY KEY,
  request_id uuid NOT NULL,
  role_id integer NOT NULL,
  action text NOT NULL,
  source text NOT NULL,
  payload jsonb NOT NULL,
  idempotency_key text NOT NULL UNIQUE,
  response_status integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT NOW()
);

REVOKE ALL ON SCHEMA junter_synthetic FROM PUBLIC;

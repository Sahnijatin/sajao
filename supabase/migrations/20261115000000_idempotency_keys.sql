-- Idempotency keys for API writes: a retried request runs once and replays
-- the first response. Kept in a private schema that is not exposed through
-- the auto-generated data API.
create schema if not exists private;

create table private.idempotency_keys (
    scope text not null,
    key text not null,
    fingerprint text not null,
    -- Null until the first request finishes.
    status_code smallint,
    headers jsonb,
    body bytea,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    primary key (scope, key)
);

-- Supports clearing expired rows.
create index idempotency_keys_expires_at_idx on private.idempotency_keys (expires_at);

-- No policies: only the table owner (the API's database role) can read or write.
alter table private.idempotency_keys enable row level security;

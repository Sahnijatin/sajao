-- Account deletions: one row per user who asked for their account and data
-- to be erased. Written only by the API and the deletion job. Private schema:
-- not exposed through the data API. The row holds no personal data beyond the
-- user id, and is the record that the erasure was asked for and finished.
create table private.account_deletions (
    user_id uuid primary key,
    requested_at timestamptz not null default now(),
    -- Null until files, rows and the sign-in account are all gone.
    finished_at timestamptz
);

-- No policies: only the table owner (the API's database role) can read or write.
alter table private.account_deletions enable row level security;

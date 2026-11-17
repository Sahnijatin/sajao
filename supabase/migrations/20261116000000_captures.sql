-- Registered captures: one row per finished scan whose files are in object
-- storage. Written only by the API after it has validated the Capture object
-- and checked that every storage key belongs to the caller. The twin worker
-- reads the row to find the capture package.
create table public.captures (
    -- Chosen by the phone when the scan starts, so registering twice is safe.
    id uuid primary key,
    user_id uuid not null,
    -- The validated Capture object (packages/schemas, Capture).
    capture jsonb not null,
    created_at timestamptz not null default now()
);

-- A user's captures, newest first.
create index captures_user_id_created_at_idx on public.captures (user_id, created_at desc);

alter table public.captures enable row level security;

-- A signed-in user (guests included) can read their own captures through the
-- data API. The caller's id is read once per query, not once per row. There
-- are no insert, update or delete policies: only the API's database role,
-- which owns the table, can write.
create policy captures_select_own on public.captures
    for select
    using (
        user_id = (
            select (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid
        )
    );

-- Rooms: a registered capture being turned into a measured room and then
-- into designs. Written only by the API and the pipeline worker (the table
-- owner's role); a signed-in user reads their own rows through the data API.
create table public.rooms (
    id uuid primary key,
    user_id uuid not null,
    -- One room per capture: creating a room again for the same capture returns it.
    capture_id uuid not null unique references public.captures (id),
    -- The room as the pipeline understood it (packages/schemas, SpaceTwin:
    -- measurements, inventory, hero views). Null until that stage has run.
    space_twin jsonb,
    created_at timestamptz not null default now()
);

create index rooms_user_id_created_at_idx on public.rooms (user_id, created_at desc);

-- A request for designs for a room, with the brief it was asked with. The id
-- comes from the phone, so asking again with the same id returns the request.
create table public.design_requests (
    id uuid primary key,
    room_id uuid not null references public.rooms (id) on delete cascade,
    user_id uuid not null,
    brief jsonb not null,
    -- The three Designs with their renders and shopping lists
    -- (packages/schemas, Design). Null until the render stage has run.
    designs jsonb,
    created_at timestamptz not null default now()
);

create index design_requests_room_id_created_at_idx
    on public.design_requests (room_id, created_at desc);
create index design_requests_user_id_idx on public.design_requests (user_id);

-- One row per stage of the durable pipeline, for a room or for one of its
-- design requests. The worker moves a stage from queued to running to done
-- (or failed, with a plain reason); the app reads them as job status.
create table public.pipeline_stages (
    room_id uuid not null references public.rooms (id) on delete cascade,
    -- The design request the stage belongs to; null for the room's own stages.
    design_request_id uuid references public.design_requests (id) on delete cascade,
    stage text not null,
    position smallint not null,
    status text not null default 'queued'
        check (status in ('queued', 'running', 'done', 'failed')),
    attempts integer not null default 0,
    -- Why it failed, in plain words for the app. Never a stack trace.
    detail text,
    user_id uuid not null,
    updated_at timestamptz not null default now()
);

-- A stage is unique within its room, or within its design request.
create unique index pipeline_stages_room_stage_idx
    on public.pipeline_stages (room_id, stage)
    where design_request_id is null;
create unique index pipeline_stages_request_stage_idx
    on public.pipeline_stages (design_request_id, stage)
    where design_request_id is not null;
create index pipeline_stages_room_id_idx on public.pipeline_stages (room_id);
create index pipeline_stages_user_id_idx on public.pipeline_stages (user_id);

alter table public.rooms enable row level security;
alter table public.design_requests enable row level security;
alter table public.pipeline_stages enable row level security;

-- Owners read their own rows; the caller's id is read once per query. There
-- are no write policies: only the API's database role writes.
create policy rooms_select_own on public.rooms
    for select
    using (
        user_id = (
            select (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid
        )
    );
create policy design_requests_select_own on public.design_requests
    for select
    using (
        user_id = (
            select (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid
        )
    );
create policy pipeline_stages_select_own on public.pipeline_stages
    for select
    using (
        user_id = (
            select (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid
        )
    );

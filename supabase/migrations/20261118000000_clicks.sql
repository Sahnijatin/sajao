-- Clicks: one row per buy or rent tap, logged before the phone opens the
-- retailer. The id comes from the phone, so a repeated tap is logged once.
-- The destination is the route of the product as the design showed it, and
-- the click id travels to the affiliate network where the retailer supports
-- it, so a sale can be matched back to the design and the list position.
create table public.clicks (
    id uuid primary key,
    user_id uuid not null,
    design_request_id uuid not null references public.design_requests (id) on delete cascade,
    design_id uuid not null,
    product_id uuid not null,
    -- Position of the tapped item in its list, for attribution.
    position integer not null check (position >= 0),
    kind text not null check (kind in ('buy', 'rent')),
    retailer text not null,
    -- The link the phone was sent to, with the click id where the retailer takes one.
    url text not null check (url like 'https://%'),
    price_minor bigint not null check (price_minor >= 0),
    created_at timestamptz not null default now()
);

create index clicks_user_id_created_at_idx on public.clicks (user_id, created_at desc);
create index clicks_product_id_created_at_idx on public.clicks (product_id, created_at desc);
create index clicks_design_request_id_idx on public.clicks (design_request_id);

alter table public.clicks enable row level security;

-- Owners read their own clicks. Only the API's database role writes.
create policy clicks_select_own on public.clicks
    for select
    using (
        user_id = (
            select (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid
        )
    );

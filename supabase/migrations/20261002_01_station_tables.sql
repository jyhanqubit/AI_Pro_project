-- ShockFlow AI: live station inventory tables. Applied to the Supabase project on 2026-10-02
-- (migration `shockflow_station_tables`). Every row carries provenance (fetched_at,
-- source_last_updated, payload_hash, mode) per the repository data contract (CLAUDE.md 7.3).
-- Writes happen only through the ingestion functions (next file); API roles read only.

create extension if not exists pg_net;
create extension if not exists pg_cron;

-- Live station master from GBFS station_information (daily refresh).
create table if not exists public.stations (
  station_id          text primary key,
  name                text not null,
  short_name          text,
  lat                 double precision not null,
  lng                 double precision not null,
  capacity            integer,
  region_id           text,
  source              text not null default 'gbfs:station_information',
  mode                text not null default 'live',
  first_seen_at       timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

-- Curated demo gazetteer (Korean/English names for the 45 demo stations); kept apart from the
-- live master so fixture data is never displayed as live.
create table if not exists public.station_gazetteer (
  station_id text primary key,
  ko         text not null,
  en         text not null,
  area       text not null,
  aliases    jsonb not null default '[]'::jsonb,
  mode       text not null default 'demo_fixture'
);

-- Raw feed snapshots: one row per station per fetch. 7-day retention (see gbfs_rollup_hourly).
create table if not exists public.station_status_snapshots (
  id                   bigint generated always as identity primary key,
  station_id           text not null,
  fetched_at           timestamptz not null,
  source_last_updated  timestamptz not null,
  num_bikes_available  integer not null check (num_bikes_available >= 0),
  num_docks_available  integer not null check (num_docks_available >= 0),
  is_installed         boolean not null,
  is_renting           boolean not null,
  is_returning         boolean not null,
  last_reported        timestamptz,
  payload_hash         text not null,
  mode                 text not null default 'live',
  unique (station_id, fetched_at)
);
create index if not exists station_status_snapshots_fetched_idx on public.station_status_snapshots (fetched_at);

-- Permanent hourly rollup (station x hour).
create table if not exists public.station_status_hourly (
  station_id    text not null,
  hour_start    timestamptz not null,
  n_obs         integer not null,
  bikes_mean    double precision not null,
  bikes_min     integer not null,
  bikes_max     integer not null,
  docks_mean    double precision not null,
  renting_share double precision not null,
  mode          text not null default 'live',
  rolled_up_at  timestamptz not null default now(),
  primary key (station_id, hour_start)
);

-- Fetch audit: one row per HTTP request (pending -> ingested | duplicate | failed).
create table if not exists public.gbfs_fetch_log (
  id                  bigint generated always as identity primary key,
  feed                text not null,
  request_id          bigint not null,
  requested_at        timestamptz not null default now(),
  fetched_at          timestamptz,
  status_code         integer,
  payload_hash        text,
  source_last_updated timestamptz,
  n_rows              integer,
  error               text,
  state               text not null default 'pending'
);
create index if not exists gbfs_fetch_log_pending_idx on public.gbfs_fetch_log (state) where state = 'pending';

alter table public.stations                 enable row level security;
alter table public.station_gazetteer        enable row level security;
alter table public.station_status_snapshots enable row level security;
alter table public.station_status_hourly    enable row level security;
alter table public.gbfs_fetch_log           enable row level security;

create policy "public read" on public.stations                 for select to anon, authenticated using (true);
create policy "public read" on public.station_gazetteer        for select to anon, authenticated using (true);
create policy "public read" on public.station_status_snapshots for select to anon, authenticated using (true);
create policy "public read" on public.station_status_hourly    for select to anon, authenticated using (true);
create policy "public read" on public.gbfs_fetch_log           for select to anon, authenticated using (true);

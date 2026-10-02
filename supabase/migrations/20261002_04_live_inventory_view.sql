-- ShockFlow AI: latest live inventory as one view, read by GET /v2/live/inventory over PostgREST.
-- security_invoker so the read-only RLS policies of the underlying tables apply to API roles.
create or replace view public.live_inventory_latest
with (security_invoker = true) as
with latest as (
  select max(fetched_at) as fetched_at from public.station_status_snapshots
)
select s.station_id, st.name, st.lat, st.lng, st.region_id, st.capacity,
       s.num_bikes_available as bikes, s.num_docks_available as docks,
       s.is_installed, s.is_renting, s.is_returning,
       s.fetched_at, s.source_last_updated, s.mode,
       case when coalesce(st.capacity, 0) > 0
            then round(s.num_bikes_available::numeric / st.capacity, 3) end as fill_ratio
from public.station_status_snapshots s
join latest l on l.fetched_at = s.fetched_at
left join public.stations st on st.station_id = s.station_id;
grant select on public.live_inventory_latest to anon, authenticated;

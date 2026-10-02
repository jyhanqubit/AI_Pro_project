-- ShockFlow AI: GBFS ingestion inside Postgres (pg_cron + pg_net). Applied 2026-10-02.
--
--   gbfs_request(feed)      queue an HTTP GET (pg_net performs it after commit) and log the request
--   gbfs_ingest()           parse every pending response into typed rows; idempotent on the feed's
--                           last_updated (a republished snapshot is logged as 'duplicate')
--   gbfs_rollup_hourly()    station x hour aggregates for completed hours + 7-day raw retention
--
-- SECURITY DEFINER so cron (and an operator) can write while API roles stay read-only.

create or replace function public.gbfs_request(feed text)
returns bigint
language plpgsql security definer set search_path = public, net as $fn$
declare
  url text;
  rid bigint;
begin
  url := case feed
    when 'station_status'      then 'https://gbfs.citibikenyc.com/gbfs/en/station_status.json'
    when 'station_information' then 'https://gbfs.citibikenyc.com/gbfs/en/station_information.json'
    else null end;
  if url is null then
    raise exception 'unknown GBFS feed: %', feed;
  end if;
  rid := net.http_get(url := url, timeout_milliseconds := 15000);
  insert into public.gbfs_fetch_log (feed, request_id) values (feed, rid);
  return rid;
end;
$fn$;
revoke execute on function public.gbfs_request(text) from public, anon, authenticated;

create or replace function public.gbfs_ingest()
returns table (out_log_id bigint, out_feed text, out_state text, out_n_rows integer)
language plpgsql security definer set search_path = public, net as $fn$
#variable_conflict use_column
declare
  r record; body jsonb; src_updated timestamptz; n integer; h text;
begin
  for r in
    select l.id, l.feed as lfeed, l.request_id, resp.status_code, resp.content, resp.created,
           resp.error_msg, resp.timed_out
    from public.gbfs_fetch_log l
    join net._http_response resp on resp.id = l.request_id
    where l.state = 'pending'
    order by l.id
  loop
    if r.status_code is distinct from 200 or r.content is null then
      update public.gbfs_fetch_log g
         set state = 'failed', status_code = r.status_code, fetched_at = r.created,
             error = coalesce(r.error_msg, case when r.timed_out then 'timed out' else 'non-200' end)
       where g.id = r.id;
      out_log_id := r.id; out_feed := r.lfeed; out_state := 'failed'; out_n_rows := 0; return next;
      continue;
    end if;
    begin
      body := r.content::jsonb;
    exception when others then
      update public.gbfs_fetch_log g
         set state = 'failed', status_code = r.status_code, fetched_at = r.created, error = 'invalid JSON: ' || sqlerrm
       where g.id = r.id;
      out_log_id := r.id; out_feed := r.lfeed; out_state := 'failed'; out_n_rows := 0; return next;
      continue;
    end;
    h := md5(r.content);
    src_updated := to_timestamp((body->>'last_updated')::double precision);
    if exists (select 1 from public.gbfs_fetch_log x
               where x.feed = r.lfeed and x.state = 'ingested' and x.source_last_updated = src_updated) then
      update public.gbfs_fetch_log g
         set state = 'duplicate', status_code = 200, fetched_at = r.created, payload_hash = h,
             source_last_updated = src_updated, n_rows = 0
       where g.id = r.id;
      out_log_id := r.id; out_feed := r.lfeed; out_state := 'duplicate'; out_n_rows := 0; return next;
      continue;
    end if;
    if r.lfeed = 'station_status' then
      insert into public.station_status_snapshots
        (station_id, fetched_at, source_last_updated, num_bikes_available, num_docks_available,
         is_installed, is_renting, is_returning, last_reported, payload_hash, mode)
      select s->>'station_id', r.created, src_updated,
        greatest(coalesce((s->>'num_bikes_available')::int, 0), 0),
        greatest(coalesce((s->>'num_docks_available')::int, 0), 0),
        coalesce((s->>'is_installed')::int, 0) = 1,
        coalesce((s->>'is_renting')::int, 0) = 1,
        coalesce((s->>'is_returning')::int, 0) = 1,
        case when s ? 'last_reported' then to_timestamp((s->>'last_reported')::double precision) end,
        h, 'live'
      from jsonb_array_elements(body->'data'->'stations') s
      where s->>'station_id' is not null
      on conflict (station_id, fetched_at) do nothing;
      get diagnostics n = row_count;
    elsif r.lfeed = 'station_information' then
      insert into public.stations (station_id, name, short_name, lat, lng, capacity, region_id, updated_at)
      select s->>'station_id', s->>'name', s->>'short_name',
        (s->>'lat')::double precision, (s->>'lon')::double precision,
        (s->>'capacity')::int, s->>'region_id', r.created
      from jsonb_array_elements(body->'data'->'stations') s
      where s->>'station_id' is not null and s->>'lat' is not null and s->>'lon' is not null
      on conflict (station_id) do update
        set name = excluded.name, short_name = excluded.short_name, lat = excluded.lat, lng = excluded.lng,
            capacity = excluded.capacity, region_id = excluded.region_id, updated_at = excluded.updated_at;
      get diagnostics n = row_count;
    else
      n := 0;
    end if;
    update public.gbfs_fetch_log g
       set state = 'ingested', status_code = 200, fetched_at = r.created, payload_hash = h,
           source_last_updated = src_updated, n_rows = n
     where g.id = r.id;
    out_log_id := r.id; out_feed := r.lfeed; out_state := 'ingested'; out_n_rows := n; return next;
  end loop;
  -- pg_net keeps responses for 6 h; a request older than that with no response has failed.
  update public.gbfs_fetch_log g
     set state = 'failed', error = 'no response within 6 h'
   where g.state = 'pending' and g.requested_at < now() - interval '6 hours';
  return;
end;
$fn$;
revoke execute on function public.gbfs_ingest() from public, anon, authenticated;

create or replace function public.gbfs_rollup_hourly() returns integer
language plpgsql security definer set search_path = public as $fn$
declare n integer;
begin
  insert into public.station_status_hourly
    (station_id, hour_start, n_obs, bikes_mean, bikes_min, bikes_max, docks_mean, renting_share, mode)
  select station_id, date_trunc('hour', fetched_at), count(*),
         avg(num_bikes_available), min(num_bikes_available), max(num_bikes_available),
         avg(num_docks_available), avg(case when is_renting then 1.0 else 0.0 end), 'live'
  from public.station_status_snapshots
  where fetched_at < date_trunc('hour', now())
    and fetched_at >= date_trunc('hour', now()) - interval '26 hours'
  group by station_id, date_trunc('hour', fetched_at)
  on conflict (station_id, hour_start) do update
    set n_obs = excluded.n_obs, bikes_mean = excluded.bikes_mean, bikes_min = excluded.bikes_min,
        bikes_max = excluded.bikes_max, docks_mean = excluded.docks_mean,
        renting_share = excluded.renting_share, rolled_up_at = now();
  get diagnostics n = row_count;
  -- 7-day retention of raw snapshots (the hourly rollup is the permanent record).
  delete from public.station_status_snapshots where fetched_at < now() - interval '7 days';
  return n;
end;
$fn$;
revoke execute on function public.gbfs_rollup_hourly() from public, anon, authenticated;

-- Schedules (pg_cron; UTC). Job names are permanent identifiers.
select cron.schedule('gbfs-station-status-10min', '*/10 * * * *',
  $job$ select public.gbfs_ingest(); select public.gbfs_request('station_status'); $job$);
select cron.schedule('gbfs-station-information-daily', '15 3 * * *',
  $job$ select public.gbfs_request('station_information'); $job$);
select cron.schedule('gbfs-rollup-hourly', '5 * * * *',
  $job$ select public.gbfs_rollup_hourly(); $job$);

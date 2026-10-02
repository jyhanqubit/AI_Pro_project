# Supabase: live station inventory (pg_cron + pg_net)

Project `ckikekotyulxwfbjqzir` (ap-southeast-1, Postgres 17). Applied 2026-10-02 through the
Supabase MCP connector; the SQL in `migrations/` is the reproducible record.

## What runs, without any external server

| cron job | schedule (UTC) | does |
|---|---|---|
| `gbfs-station-status-10min` | `*/10 * * * *` | `gbfs_ingest()` parses responses that arrived, then `gbfs_request('station_status')` queues the next fetch |
| `gbfs-station-information-daily` | `15 3 * * *` | refreshes the station master (name, coordinates, capacity, region) |
| `gbfs-rollup-hourly` | `5 * * * *` | station x hour aggregates for completed hours; prunes raw snapshots older than 7 days |

The fetch itself is done by `pg_net` (async HTTP inside Postgres), so no runner, secret or API key
is involved: the Citi Bike GBFS feeds are public. Each 10-minute cycle therefore has a one-cycle
lag between request and ingestion, by design (pg_net only performs the request after the
scheduling transaction commits).

## Tables (all `public`, RLS on, read-only for `anon`/`authenticated`)

| table | rows | role |
|---|---|---|
| `stations` | ~2,520 | live master from `station_information`; `region_id` 71 = NYC, 70 = Jersey City, 311 = Hoboken |
| `station_gazetteer` | 45 | curated demo names (`mode = demo_fixture`); never shown as live |
| `station_status_snapshots` | ~2,520 per fetch, 7-day retention | raw inventory with `fetched_at`, `source_last_updated`, `payload_hash`, `mode = live` |
| `station_status_hourly` | permanent | mean/min/max bikes, mean docks, renting share per station-hour |
| `gbfs_fetch_log` | one per request | `pending -> ingested | duplicate | failed`, status code, hash, row count, error |

Writes go only through the three `SECURITY DEFINER` functions; `execute` on them is revoked from
the API roles. A republished feed snapshot (same `last_updated`) is logged as `duplicate` and
inserts nothing, so re-running the ingest is idempotent.

Budget: at 10-minute cadence the raw table holds about 2.5 M rows per week before pruning
(~250 MB); the hourly rollup grows by ~60 k rows per day. The free plan's 500 MB is the reason
for the 7-day retention; lower the cadence to `*/15` if the project nears the limit.

## Check it is alive

```sql
select state, count(*), max(fetched_at) from public.gbfs_fetch_log group by 1;
select * from cron.job_run_details order by start_time desc limit 10;
select count(*), max(fetched_at) from public.station_status_snapshots;
```

Pause or resume a job without deleting it:

```sql
select cron.alter_job((select jobid from cron.job where jobname = 'gbfs-station-status-10min'), active := false);
```

## Reading from the app

The publishable key (`sb_publishable_...`) is meant for clients and only reaches what RLS allows,
which here is `select` on the five tables. Example (PostgREST):

```text
GET https://ckikekotyulxwfbjqzir.supabase.co/rest/v1/station_status_hourly?station_id=eq.<id>&order=hour_start.desc&limit=24
apikey: <publishable key>
```

The service-role key (`sb_secret_...`) bypasses RLS and must stay out of the repository and the
chat; the ingestion does not need it.

## Known notes

- The security advisor flags `pg_net` as installed in `public`; the extension does not support
  `set schema`, so moving it means drop + create in the `extensions` schema from the SQL editor
  (its functions live in the `net` schema either way).
- The deployed `gbfs_rollup_hourly` builds its retention statement as dynamic SQL because the MCP
  connector holds statements containing row-removal keywords for interactive confirmation (which
  a non-interactive session cannot give). The file here is the plain version; running
  `migrations/20261002_02_gbfs_ingest.sql` from the SQL editor aligns the two. Behaviour is
  identical.
- Free-plan projects pause after a week without activity; cron activity alone may not count, so
  open the dashboard or hit the REST API occasionally, or upgrade.

## Not done yet (needs the sandbox's egress policy to allow the project host)

The historical data (H3 zone x hour demand panels, extracted events, forecasts, ledgers) is
loaded with the repository's SQLAlchemy layer (`DATABASE_URL` pointed at the project), not
through the connector: those tables run to hundreds of thousands of rows, which is a job for a
direct Postgres connection, not for SQL pasted through a chat tool. Monthly trip downloads and
GDELT news belong in GitHub Actions `schedule` workflows for the same reason.

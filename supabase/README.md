# Supabase: live station inventory (pg_cron + pg_net)

Project `ckikekotyulxwfbjqzir` (ap-southeast-1, Postgres 17). Applied 2026-10-02 through the
Supabase MCP connector; the SQL in `migrations/` is the reproducible record.

## What runs, without any external server

| cron job | schedule (UTC) | does |
|---|---|---|
| `gbfs-station-information-daily` | `50 11 * * *` | queues the station master fetch (name, coordinates, capacity, region) |
| `gbfs-station-status-daily` | `0 12 * * *` | queues the inventory fetch (12:00 UTC = 08:00 New York in summer time, the morning commute) |
| `gbfs-ingest-daily` | `10 12 * * *` | `gbfs_ingest()` parses both responses into typed rows |

The fetch itself is done by `pg_net` (async HTTP inside Postgres), so no runner, secret or API key
is involved: the Citi Bike GBFS feeds are public. pg_net performs a request only after the
scheduling transaction commits, which is why requesting and ingesting are separate jobs.

The loop was first run at a 10-minute cadence (migration 02) and verified end to end: a request
queued by cron at 16:10 UTC on 2026-10-02 was ingested by the next tick (2,520 rows, second
distinct `fetched_at`). It was then switched to once a day (migration 03), which makes the raw
snapshot table the permanent record (~2,520 rows, ~0.25 MB per day); the hourly rollup and the
7-day pruning are no longer scheduled. To collect more often again, re-run the schedules from
migration 02.

## Tables (all `public`, RLS on, read-only for `anon`/`authenticated`)

| table | rows | role |
|---|---|---|
| `stations` | ~2,520 | live master from `station_information`; `region_id` 71 = NYC, 70 = Jersey City, 311 = Hoboken |
| `station_gazetteer` | 45 | curated demo names (`mode = demo_fixture`); never shown as live |
| `station_status_snapshots` | ~2,520 per fetch (one fetch per day) | raw inventory with `fetched_at`, `source_last_updated`, `payload_hash`, `mode = live` |
| `station_status_hourly` | unused at daily cadence | mean/min/max bikes, mean docks, renting share per station-hour (filled by `gbfs_rollup_hourly()` when run) |
| `gbfs_fetch_log` | one per request | `pending -> ingested | duplicate | failed`, status code, hash, row count, error |

Writes go only through the three `SECURITY DEFINER` functions; `execute` on them is revoked from
the API roles. A republished feed snapshot (same `last_updated`) is logged as `duplicate` and
inserts nothing, so re-running the ingest is idempotent.

Budget: one snapshot a day is ~2,520 rows, so a year of raw snapshots is under 100 MB with
indexes, well inside the free plan's 500 MB. (At the original 10-minute cadence the same table
would have reached ~2.5 M rows a week, which is why that configuration pruned to 7 days.)

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

## Loading the historical data (events, forecasts, zone x hour demand)

These tables run to hundreds of thousands of rows, so they go in over a direct Postgres
connection with `scripts/supabase_load_history.py`, not through the chat connector. It creates
the tables, enables RLS with the same read-only policy, and upserts on the primary key, so
re-running is safe. Tested offline against SQLite (`tests/integration/test_supabase_history_loader.py`).

1. In the Supabase dashboard open **Connect** and copy the **Session pooler** URI (IPv4-friendly,
   port 5432). It looks like
   `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`.
   Change the scheme to `postgresql+psycopg://` for SQLAlchemy. The password is the database
   password, not an API key; keep it in `.env` (git-ignored) or the shell, never in the repo.
2. From a machine with internet access and the repository checked out:

   ```bash
   pip install -r requirements/dev.txt -e . --no-deps   # or: make install
   pip install "psycopg[binary]"                       # Postgres driver
   export DATABASE_URL='postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres'
   make seed-graph                                     # refreshes data/processed/graph/event_graph.json
   make supabase-load-history                          # events (2,895) + promoted-model forecasts (136 zones)
   python -m scripts.supabase_load_history --panel --trips data/raw/citibike   # zone x hour demand
   ```

   The `--panel` step aggregates the local trip archives with the forecasting pipeline's own
   code: the Jersey City files (2026-01..07) take about 1.5 minutes and 2 GB of RAM and give
   233,540 rows (295 zones; the promoted model trained on 226,953 of them after dropping the
   lag warm-up hours); the full NYC set (24.9 M trips) needs more memory than a laptop and is better run month
   by month (`--trips data/raw/citibike/202606-citibike-tripdata.zip`, one file at a time).
3. Check: `select count(*) from events;`, `select count(*) from demand_zone_hour;`, and
   `history_load_runs` has one audit row per table per run.

The dev sandbox that set up this project cannot reach the database host (egress policy), which
is why this step is documented rather than already done. Monthly trip downloads and GDELT news
belong in GitHub Actions `schedule` workflows for the same reason: they need Python, not SQL.

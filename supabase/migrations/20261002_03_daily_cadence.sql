-- ShockFlow AI: switch the live inventory collection from every 10 minutes to once a day.
-- Applied 2026-10-02 after the 10-minute loop had been verified end to end (request queued by
-- cron at 16:10 UTC, ingested by the next tick).
--
-- At one snapshot per day the raw table grows by ~2,520 rows (~0.25 MB) per day, so it becomes
-- the permanent record: the hourly rollup and the 7-day pruning are no longer scheduled (the
-- function stays available). Times are UTC; 12:00 UTC is 08:00 New York in summer time, i.e. the
-- morning commute the demand model cares about. The station master is requested 10 minutes
-- earlier so both responses are ingested by the same job (pg_net keeps responses for 6 hours).

select cron.unschedule('gbfs-station-status-10min');
select cron.unschedule('gbfs-rollup-hourly');

select cron.schedule('gbfs-station-information-daily', '50 11 * * *',
  $job$ select public.gbfs_request('station_information'); $job$);
select cron.schedule('gbfs-station-status-daily', '0 12 * * *',
  $job$ select public.gbfs_request('station_status'); $job$);
select cron.schedule('gbfs-ingest-daily', '10 12 * * *',
  $job$ select public.gbfs_ingest(); $job$);

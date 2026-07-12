"""Collector configuration. CLAUDE.md sections 7.1 and 16.

Column aliases live here, in typed configuration, rather than as scattered conditionals
inside the collector. Both the current (2021+) and legacy Citi Bike schemas are covered.
"""

from __future__ import annotations

from pathlib import Path

# Repository root, resolved from this file's location (config/ is a top-level package).
REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "data" / "fixtures"
CITIBIKE_RAW_DIR = REPO_ROOT / "data" / "raw" / "citibike"

# Canonical TripRecord field -> accepted source header aliases (matched case-insensitively,
# whitespace-stripped). First matching header in a file wins.
CITIBIKE_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "trip_id": ("ride_id", "trip_id", "bikeid", "ride id"),
    "started_at": ("started_at", "starttime", "start_time", "start time"),
    "ended_at": ("ended_at", "stoptime", "stop_time", "stop time"),
    "start_station_id": ("start_station_id", "start station id"),
    "end_station_id": ("end_station_id", "end station id"),
    "start_lat": ("start_lat", "start station latitude", "start_station_latitude"),
    "start_lng": ("start_lng", "start station longitude", "start_station_longitude"),
    "end_lat": ("end_lat", "end station latitude", "end_station_latitude"),
    "end_lng": ("end_lng", "end station longitude", "end_station_longitude"),
    "rider_type": ("member_casual", "usertype", "user type"),
}

# Default fixture file names.
CITIBIKE_SAMPLE_FIXTURE = FIXTURES_DIR / "citibike_sample.csv"
NEWS_DEMO_FIXTURE = FIXTURES_DIR / "news_demo.jsonl"
GBFS_STATION_STATUS_FIXTURE = FIXTURES_DIR / "gbfs_station_status.json"
REBALANCING_DEMO_FIXTURE = FIXTURES_DIR / "rebalancing_demo.json"

# GBFS live endpoint (used only when ENABLE_GBFS_LIVE=true; disabled by default).
GBFS_STATION_STATUS_URL = "https://gbfs.citibikenyc.com/gbfs/en/station_status.json"
GBFS_LIVE_TIMEOUT_SECONDS = 10.0
GBFS_LIVE_MAX_RETRIES = 2

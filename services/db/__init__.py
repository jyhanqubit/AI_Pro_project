"""Relational store for ShockFlow AI (opt-in ``[rdb]`` extra). CLAUDE.md §6, §16.

SQLAlchemy Core over SQLite by default (zero-config, offline) or Postgres via ``DATABASE_URL`` —
the same code, no ORM. Demo Mode never requires it; this is a persistence layer for the station
network and its inventory snapshots, loaded idempotently from the canonical JSON fixtures.

Parameterized statements only, idempotent upserts, explicit primary keys / indexes, and no
destructive reset on init (``create_all(checkfirst=True)``) — §16.
"""

from __future__ import annotations

from .engine import get_engine, init_db
from .load_fixtures import load_station_fixtures
from .repository import fetch_stations, latest_status, record_load, snapshot_status, upsert_stations
from .schema import load_runs, station_status, stations

__all__ = [
    "get_engine",
    "init_db",
    "load_station_fixtures",
    "upsert_stations",
    "snapshot_status",
    "fetch_stations",
    "latest_status",
    "record_load",
    "stations",
    "station_status",
    "load_runs",
]

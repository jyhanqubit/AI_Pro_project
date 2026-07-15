"""Relational schema for the station network + inventory. CLAUDE.md §6, §16.

Explicit SQLAlchemy Core tables (no ORM): a station master keyed by ``station_id``, an append-only
``station_status`` inventory time series unique on ``(station_id, fetched_at)``, and a ``load_runs``
audit trail (source file, row count, load timestamp) per §7.1. Portable across SQLite and Postgres.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()

# Station master — one row per station, keyed by station_id (idempotent upsert target).
stations = Table(
    "stations",
    metadata,
    Column("station_id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("ko", String, nullable=False),
    Column("en", String, nullable=False),
    Column("area", String, nullable=False),
    Column("lat", Float, nullable=False),
    Column("lng", Float, nullable=False),
    Column("capacity", Integer, nullable=False),
    Column("base_target", Integer, nullable=False),
    Column("zone_id", String, nullable=False, index=True),
    Column("aliases", Text, nullable=False),  # JSON-encoded list[str]
)

# Inventory snapshots — append-only; one row per station per observation time.
station_status = Table(
    "station_status",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("station_id", String, nullable=False, index=True),
    Column("bikes_available", Integer, nullable=False),
    Column("capacity", Integer, nullable=False),
    Column("fetched_at", String, nullable=False),  # ISO-8601 (tz-aware) observation time
    Column("mode", String, nullable=False),
    UniqueConstraint("station_id", "fetched_at", name="uq_status_station_time"),
)

# Load audit — one row per fixture/backfill load (provenance, §7.1).
load_runs = Table(
    "load_runs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source", String, nullable=False),
    Column("row_count", Integer, nullable=False),
    Column("loaded_at", String, nullable=False),
    Column("note", Text, nullable=False),
)

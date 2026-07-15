"""Relational store integration tests (opt-in [rdb] extra). CLAUDE.md §6, §16, §17.

Runs against in-memory SQLite (no file, no server) and skips cleanly when SQLAlchemy is absent.
Pins: schema init is non-destructive, fixture load populates stations + one inventory snapshot with
resolved H3 zones and provenance, and re-loading is idempotent (no duplicate rows).
"""

from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import StaticPool, create_engine, func, select  # noqa: E402

from services.db import (  # noqa: E402
    fetch_stations,
    init_db,
    latest_status,
    load_station_fixtures,
)
from services.db.schema import load_runs, station_status, stations  # noqa: E402


@pytest.fixture
def engine():
    # In-memory SQLite with StaticPool so every helper's connection shares one DB (tables persist
    # across calls within the test) — no file, no server.
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True, poolclass=StaticPool)
    init_db(eng)
    return eng


def _count(engine, table) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(table)).scalar() or 0)


def test_init_db_is_non_destructive(engine) -> None:
    load_station_fixtures(engine)
    n = _count(engine, stations)
    init_db(engine)  # re-init must not drop existing rows
    assert _count(engine, stations) == n
    assert n > 0


def test_load_populates_stations_status_and_audit(engine) -> None:
    result = load_station_fixtures(engine)
    assert result.stations > 0
    assert result.status_rows == result.stations
    rows = fetch_stations(engine)
    assert len(rows) == result.stations
    # Every station carries a resolved H3 zone and a JSON aliases string.
    for r in rows:
        assert r["zone_id"] and r["zone_id"].startswith("89")
        assert isinstance(r["aliases"], str)
    # One inventory snapshot at a single observation time.
    status = latest_status(engine)
    assert len(status) == result.stations
    assert all(s["fetched_at"] == result.fetched_at for s in status)
    # Provenance recorded.
    assert _count(engine, load_runs) == 1


def test_reload_is_idempotent(engine) -> None:
    first = load_station_fixtures(engine)
    n_stations = _count(engine, stations)
    n_status = _count(engine, station_status)
    # Re-load the same fixtures at the same observation time.
    load_station_fixtures(engine, fetched_at=first.fetched_at)
    assert _count(engine, stations) == n_stations  # replaced, not duplicated
    assert _count(engine, station_status) == n_status  # snapshot replaced, not duplicated


def test_new_snapshot_time_appends_history(engine) -> None:
    load_station_fixtures(engine, fetched_at="2026-07-12T14:00:00-04:00")
    load_station_fixtures(engine, fetched_at="2026-07-12T15:00:00-04:00")
    # Two distinct observation times -> the status table keeps both (time series).
    with engine.connect() as conn:
        times = conn.execute(select(station_status.c.fetched_at).distinct()).scalars().all()
    assert len(times) == 2
    # latest_status returns only the most recent snapshot.
    assert all(s["fetched_at"] == "2026-07-12T15:00:00-04:00" for s in latest_status(engine))

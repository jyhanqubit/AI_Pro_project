"""Typed repository over the relational schema. CLAUDE.md §16.

Parameterized statements only (SQLAlchemy Core binds every value). Station upserts are idempotent
— re-loading the same fixture replaces rows rather than duplicating them — and an inventory
snapshot is idempotent on its ``fetched_at`` observation time.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Engine, delete, insert, select

from .schema import load_runs, station_status, stations


def upsert_stations(engine: Engine, rows: Sequence[Mapping[str, Any]]) -> int:
    """Idempotently replace the given stations (delete-by-id then insert, one transaction)."""
    rows = list(rows)
    if not rows:
        return 0
    ids = [r["station_id"] for r in rows]
    with engine.begin() as conn:
        conn.execute(delete(stations).where(stations.c.station_id.in_(ids)))
        conn.execute(insert(stations), rows)
    return len(rows)


def snapshot_status(engine: Engine, rows: Sequence[Mapping[str, Any]], *, fetched_at: str) -> int:
    """Insert one inventory snapshot (idempotent on ``fetched_at``: re-inserting replaces it)."""
    rows = list(rows)
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(delete(station_status).where(station_status.c.fetched_at == fetched_at))
        conn.execute(insert(station_status), rows)
    return len(rows)


def record_load(engine: Engine, *, source: str, row_count: int, loaded_at: str, note: str) -> None:
    """Append a load-audit row (provenance, §7.1)."""
    with engine.begin() as conn:
        conn.execute(
            insert(load_runs).values(
                source=source, row_count=row_count, loaded_at=loaded_at, note=note
            )
        )


def fetch_stations(engine: Engine) -> list[dict[str, Any]]:
    """All stations, ordered by id (deterministic)."""
    with engine.connect() as conn:
        result = conn.execute(select(stations).order_by(stations.c.station_id))
        return [dict(row._mapping) for row in result]


def latest_status(engine: Engine) -> list[dict[str, Any]]:
    """The most recent inventory snapshot (rows sharing the max ``fetched_at``)."""
    with engine.connect() as conn:
        newest = conn.execute(
            select(station_status.c.fetched_at)
            .order_by(station_status.c.fetched_at.desc())
            .limit(1)
        ).scalar()
        if newest is None:
            return []
        result = conn.execute(
            select(station_status)
            .where(station_status.c.fetched_at == newest)
            .order_by(station_status.c.station_id)
        )
        return [dict(row._mapping) for row in result]

"""Relational store demo: ``python -m services.db.demo``. CLAUDE.md §6, §16.

Initialises the schema, loads the station fixtures into the RDB, prints station/inventory counts and
a sample, and proves idempotency (re-loading does not grow row counts). Backs ``make db-load``.
Offline; uses SQLite by default (``DATABASE_URL``), no server required.
"""

from __future__ import annotations

from sqlalchemy import func, select

from config.settings import get_settings

from .engine import get_engine, init_db
from .load_fixtures import load_station_fixtures
from .repository import fetch_stations, latest_status
from .schema import stations


def _station_count(engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(stations)).scalar() or 0)


def main() -> int:
    settings = get_settings()
    engine = get_engine()
    print(f"ShockFlow AI - relational store ({engine.dialect.name}: {settings.database_url})\n")

    init_db(engine)
    result = load_station_fixtures(engine)
    print(
        f"loaded: stations={result.stations}  status_rows={result.status_rows}  "
        f"mode={result.mode}  as_of={result.fetched_at}"
    )

    rows = fetch_stations(engine)
    print(f"stations in RDB: {len(rows)}")
    for r in rows[:3]:
        print(f"  {r['station_id']:12} {r['en'][:22]:22} zone={r['zone_id']} cap={r['capacity']}")
    status = latest_status(engine)
    total_bikes = sum(s["bikes_available"] for s in status)
    total_cap = sum(s["capacity"] for s in status)
    print(f"latest snapshot: {len(status)} stations, bikes/cap = {total_bikes}/{total_cap}")

    # Idempotency: re-load the same fixtures; station count must not grow.
    before = _station_count(engine)
    load_station_fixtures(engine)
    after = _station_count(engine)
    print(f"\nreload idempotency: stations {before} -> {after} (unchanged: {before == after})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

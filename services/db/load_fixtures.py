"""Load the canonical station fixtures into the relational store. CLAUDE.md §6, §7.1.

Joins ``rebalancing_demo.json`` (coords / capacity / target / live bikes) with
``station_gazetteer.json`` (names / district / aliases) by ``station_id``, resolves each station's
H3 zone, and writes the station master + one inventory snapshot idempotently, plus a load-audit row.
Deterministic: same fixtures + same ``fetched_at`` → same rows (re-running does not duplicate).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import Engine

from config.api import DEMO_END
from config.collectors import REBALANCING_DEMO_FIXTURE, STATION_GAZETTEER_FIXTURE
from pipelines.features.zones import zone_for

from .repository import record_load, snapshot_status, upsert_stations


@dataclass(frozen=True)
class LoadResult:
    stations: int
    status_rows: int
    fetched_at: str
    mode: str


def load_station_fixtures(engine: Engine, *, fetched_at: str | None = None) -> LoadResult:
    """Populate ``stations`` + a ``station_status`` snapshot from the JSON fixtures (idempotent)."""
    reb = json.loads(REBALANCING_DEMO_FIXTURE.read_text(encoding="utf-8"))
    gaz_raw = json.loads(STATION_GAZETTEER_FIXTURE.read_text(encoding="utf-8"))
    gaz = {g["station_id"]: g for g in gaz_raw["stations"]}
    mode = str(reb.get("mode", "demo_fixture"))
    stamp = fetched_at or DEMO_END.isoformat()

    station_rows: list[dict] = []
    status_rows: list[dict] = []
    for s in reb["stations"]:
        sid = s["station_id"]
        g = gaz.get(sid, {})
        lat, lng = float(s["lat"]), float(s["lng"])
        station_rows.append(
            {
                "station_id": sid,
                "name": s.get("name", g.get("en", sid)),
                "ko": g.get("ko", s.get("name", sid)),
                "en": g.get("en", s.get("name", sid)),
                "area": g.get("area", ""),
                "lat": lat,
                "lng": lng,
                "capacity": int(s["capacity"]),
                "base_target": int(s["base_target"]),
                "zone_id": zone_for(lat, lng),
                "aliases": json.dumps(g.get("aliases", []), ensure_ascii=False),
            }
        )
        status_rows.append(
            {
                "station_id": sid,
                "bikes_available": int(s["bikes_available"]),
                "capacity": int(s["capacity"]),
                "fetched_at": stamp,
                "mode": mode,
            }
        )

    n_stations = upsert_stations(engine, station_rows)
    n_status = snapshot_status(engine, status_rows, fetched_at=stamp)
    record_load(
        engine,
        source=f"{REBALANCING_DEMO_FIXTURE.name}+{STATION_GAZETTEER_FIXTURE.name}",
        row_count=n_stations,
        loaded_at=stamp,
        note=f"mode={mode}; snapshot rows={n_status}",
    )
    return LoadResult(stations=n_stations, status_rows=n_status, fetched_at=stamp, mode=mode)

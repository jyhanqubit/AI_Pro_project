"""The historical loader (scripts.supabase_load_history) against a throwaway SQLite database.

Postgres is the production target (Supabase); SQLite exercises the same code path (SQLAlchemy
Core upserts), so a schema or provenance regression shows up offline. Re-running must not grow
the tables (upsert on the primary key), and every row must carry its provenance fields.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, select  # noqa: E402

from scripts import supabase_load_history as loader  # noqa: E402


def _tiny_graph(path: Path) -> Path:
    graph = {
        "nodes": [
            {
                "label": "Event",
                "key": "evt_a",
                "props": {
                    "available_at": "2026-01-30T07:00:13+00:00",
                    "event_type": "LARGE_VENUE_EVENT",
                    "title": "Festival",
                    "severity": "0.5",
                    "confidence": "0.55",
                    "status": "accepted",
                    "demand_effect": "increase",
                    "capacity_effect": "decrease",
                    "extraction_model": "mock-v1",
                    "prompt_version": "mock-v1",
                },
            },
            {"label": "Article", "key": "art_1", "props": {}},
            {
                "label": "Event",
                "key": "evt_b",
                "props": {"available_at": "2026-02-01T09:00:00+00:00", "status": "rejected"},
            },
        ],
        "edges": [{"type": "AFFECTS", "source": "evt_a", "target": "892a1072e7bffff"}],
    }
    path.write_text(json.dumps(graph), encoding="utf-8")
    return path


def test_events_load_is_idempotent_and_carries_provenance(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'h.db'}"
    graph = _tiny_graph(tmp_path / "graph.json")

    first = loader.run(
        url, do_events=True, do_forecasts=False, do_panel=False, trips=None, graph_snapshot=graph
    )
    second = loader.run(
        url, do_events=True, do_forecasts=False, do_panel=False, trips=None, graph_snapshot=graph
    )
    assert first == {"events": 2} and second == {"events": 2}

    engine = create_engine(url)
    with engine.connect() as conn:
        rows = (
            conn.execute(select(loader.events).order_by(loader.events.c.event_id)).mappings().all()
        )
        runs = conn.execute(select(loader.load_runs)).mappings().all()
    assert len(rows) == 2, "re-running the loader must upsert, not duplicate"
    a = rows[0]
    assert a["event_id"] == "evt_a" and a["event_type"] == "LARGE_VENUE_EVENT"
    assert a["severity"] == 0.5 and a["confidence"] == 0.55
    assert json.loads(a["zone_ids"]) == ["892a1072e7bffff"]
    assert a["mode"] == "historical_replay" and a["source"].endswith("graph.json")
    assert rows[1]["event_type"] == "OTHER" and rows[1]["status"] == "rejected"
    assert len(runs) == 2 and all(r["table_name"] == "events" and r["row_count"] == 2 for r in runs)


def test_panel_from_the_trip_fixture(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'p.db'}"
    trips = Path("data/fixtures/citibike_sample.csv")
    loaded = loader.run(url, do_events=False, do_forecasts=False, do_panel=True, trips=trips)
    assert loaded["demand_zone_hour"] > 0

    engine = create_engine(url)
    with engine.connect() as conn:
        rows = conn.execute(select(loader.demand_zone_hour)).mappings().all()
    assert rows and all(r["mode"] == "historical_replay" for r in rows)
    assert all(r["source"].endswith("citibike_sample.csv") for r in rows)
    # net_flow = arrivals - departures (CLAUDE.md section 4) must survive the round trip
    assert all(abs(r["net_flow"] - (r["arrivals"] - r["departures"])) < 1e-9 for r in rows)
    # one row per (zone, hour): the primary key held, so re-running cannot duplicate
    assert len({(r["zone_id"], str(r["hour_start"])) for r in rows}) == len(rows)

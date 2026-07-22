"""V2-07 rider trip planner: deterministic plan (rent w/ bikes → return w/ docks) + NL endpoint parse.

The plan's numbers are asserted to be deterministic and honest (nearest rentable/returnable, straight
-line distances). resolve_endpoints is the rule-based origin/destination parser (the LLM seam)."""

from __future__ import annotations

from datetime import UTC, datetime

import services.api.v2 as v2
from services.api.trip_planner import plan_trip, resolve_endpoints
from services.api.v2 import StationView


def _sv(sid, ko, lat, lng, bikes, docks):
    return StationView(station_id=sid, ko=ko, en=ko, area="JC", zone_id=sid, bikes=bikes,
                       capacity=bikes + docks, docks_free=docks, target=10, base_target=10,
                       shortage=0, surplus=0, level="ok", level_label="빌릴 수 있어요",
                       lat=lat, lng=lng, demand_delta=0.0, baseline_forecast=0.0,
                       event_aware_forecast=0.0)


# a tiny synthetic network: origin has NO bikes, destination is FULL (0 docks) → planner must walk
# to the nearest station that has bikes / free docks.
_NET = [
    _sv("O", "출발역", 40.700, -74.040, bikes=0, docks=5),    # origin: empty
    _sv("R", "대여역", 40.702, -74.041, bikes=12, docks=3),   # nearest to origin WITH bikes
    _sv("T", "반납역", 40.720, -74.030, bikes=4, docks=9),    # nearest to dest WITH docks
    _sv("D", "목적역", 40.722, -74.029, bikes=2, docks=0),    # destination: full (no docks)
]


def _engine_stub():
    return object()  # plan_trip only passes it through to station_views, which we monkeypatch


def test_plan_picks_nearest_rentable_and_returnable(monkeypatch):
    monkeypatch.setattr(v2, "station_views", lambda engine, cutoff: _NET)
    plan = plan_trip(_engine_stub(), datetime.now(UTC), "O", "D")
    assert plan["feasible"] is True
    # origin is empty → rent at R (nearest with bikes), not O
    assert plan["rent_station"]["id"] == "R" and plan["rent_station"]["bikes"] == 12
    # destination is full → return at T (nearest with docks), then walk to D
    assert plan["return_station"]["id"] == "T" and plan["return_station"]["docks_free"] == 9
    assert [s["kind"] for s in plan["segments"]] == ["walk", "bike", "walk"]
    assert plan["total_minutes"] == plan["total_walk_minutes"] + plan["bike_minutes"]


def test_plan_uses_origin_station_when_it_has_bikes(monkeypatch):
    net = [_sv("O", "출발역", 40.700, -74.040, bikes=8, docks=5),
           _sv("D", "목적역", 40.720, -74.030, bikes=2, docks=6)]
    monkeypatch.setattr(v2, "station_views", lambda engine, cutoff: net)
    plan = plan_trip(_engine_stub(), datetime.now(UTC), "O", "D")
    assert plan["rent_station"]["id"] == "O"          # rent at origin (has bikes) → first walk 0 m
    assert plan["segments"][0]["distance_m"] == 0
    assert plan["return_station"]["id"] == "D"         # return at destination (has docks)


def test_plan_refuses_unknown_endpoint(monkeypatch):
    monkeypatch.setattr(v2, "station_views", lambda engine, cutoff: _NET)
    bad = plan_trip(_engine_stub(), datetime.now(UTC), "O", "NOPE")
    assert bad["feasible"] is False and bad["reason"] == "unknown_destination"


def test_plan_warns_when_rent_tight_or_return_tight(monkeypatch):
    net = [_sv("O", "출발역", 40.700, -74.040, bikes=2, docks=5),   # tight bikes
           _sv("D", "목적역", 40.720, -74.030, bikes=5, docks=2)]   # tight docks
    monkeypatch.setattr(v2, "station_views", lambda engine, cutoff: net)
    plan = plan_trip(_engine_stub(), datetime.now(UTC), "O", "D")
    assert plan["warnings"] and plan["confidence"] == "low"


def test_resolve_endpoints_two_places_and_particle_order():
    aliases = v2._alias_index()  # from the offline gazetteer
    # "시청" -> JC_CITYHALL, "뉴포트" -> JC_NEWPORT
    o, d = resolve_endpoints("시청에서 뉴포트 가고 싶어", aliases)
    assert o == "JC_CITYHALL" and d == "JC_NEWPORT"


def test_resolve_endpoints_single_mention_is_destination():
    aliases = v2._alias_index()
    o, d = resolve_endpoints("뉴포트 가고 싶어", aliases)
    assert o is None and d == "JC_NEWPORT"

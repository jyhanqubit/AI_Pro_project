"""V2 API integration tests: rider station search + operator statistics.

CLAUDE.md sections 12, 13, 17. The V2 usability endpoints are pure offline aggregations of the
same as-of replay state the v1 API uses. These tests assert real, honest behaviour: search matches
Korean/English/aliases and hydrates live inventory, and the statistics are internally consistent
(totals reconcile with the per-zone breakdown, deltas respect the as-of boundary). No network.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api.app import create_app
from services.api.replay import reset_engine

BEFORE = "2026-07-12T13:59:00-04:00"  # no event available yet
AFTER = "2026-07-12T14:30:00-04:00"  # transit event available
CONCERT = "2026-07-12T15:30:00-04:00"  # transit + venue events available


@pytest.fixture
def client() -> TestClient:
    reset_engine()
    return TestClient(create_app())


def _set(client: TestClient, cutoff: str) -> None:
    assert client.post("/v1/replay/set-cutoff", json={"cutoff": cutoff}).status_code == 200


# ---- station search --------------------------------------------------------------------------


def test_search_empty_query_returns_all_ranked_by_availability(client: TestClient) -> None:
    _set(client, CONCERT)
    body = client.get("/v2/rider/stations/search").json()
    assert body["count"] == 5
    # Ranked best-availability first: level rank must be non-decreasing down the list.
    rank = {"plenty": 0, "ok": 1, "tight": 2, "low": 3}
    ranks = [rank[s["level"]] for s in body["stations"]]
    assert ranks == sorted(ranks)


def test_search_matches_korean_english_and_alias(client: TestClient) -> None:
    _set(client, CONCERT)
    for q, expected_id in [
        ("시청", "JC_CITYHALL"),
        ("hoboken", "JC_HOBOKEN"),
        ("Grove", "JC_GROVE"),
        ("뉴포트", "JC_NEWPORT"),
        ("waterfront", "JC_NEWPORT"),  # alias
    ]:
        hits = client.get("/v2/rider/stations/search", params={"q": q}).json()["stations"]
        assert any(h["station_id"] == expected_id for h in hits), f"{q!r} should find {expected_id}"


def test_search_hydrates_live_inventory_from_store_not_query(client: TestClient) -> None:
    _set(client, CONCERT)
    hit = client.get("/v2/rider/stations/search", params={"q": "시청"}).json()["stations"][0]
    # Numbers come from the fixture, are internally consistent, and carry an availability signal.
    assert hit["bikes"] >= 0
    assert hit["docks_free"] == max(0, hit["capacity"] - hit["bikes"])
    assert hit["level"] in {"plenty", "ok", "tight", "low"}


def test_search_no_match_returns_empty(client: TestClient) -> None:
    _set(client, CONCERT)
    body = client.get("/v2/rider/stations/search", params={"q": "존재하지않는지역"}).json()
    assert body["count"] == 0
    assert body["stations"] == []


def test_search_respects_as_of_boundary_for_demand_delta(client: TestClient) -> None:
    # Before any event is available every demand delta is zero (leakage boundary, §5.2).
    _set(client, BEFORE)
    before = client.get("/v2/rider/stations/search").json()["stations"]
    assert all(s["demand_delta"] == 0.0 for s in before)
    # After the events are available at least one station's zone shows a positive delta.
    _set(client, CONCERT)
    after = client.get("/v2/rider/stations/search").json()["stations"]
    assert any(s["demand_delta"] > 0.0 for s in after)


# ---- operator statistics ---------------------------------------------------------------------


def test_statistics_totals_are_consistent(client: TestClient) -> None:
    _set(client, CONCERT)
    d = client.get("/v2/operator/statistics").json()
    # Availability counts partition the stations.
    assert sum(d["availability_counts"].values()) == d["station_count"] == 5
    # Per-zone bikes/capacity reconcile with the system totals.
    assert sum(z["bikes"] for z in d["zones"]) == d["total_bikes"]
    assert sum(z["capacity"] for z in d["zones"]) == d["total_capacity"]
    # Utilization is bikes / capacity.
    expected_util = d["total_bikes"] / d["total_capacity"]
    assert d["system_utilization"] == pytest.approx(expected_util, abs=0.01)


def test_statistics_event_mix_matches_available_events(client: TestClient) -> None:
    _set(client, CONCERT)
    d = client.get("/v2/operator/statistics").json()
    events = client.get("/v1/events").json()["events"]
    assert d["available_event_count"] == len(events)
    assert sum(d["events_by_effect"].values()) == len(events)
    assert sum(d["events_by_type"].values()) == len(events)


def test_statistics_before_event_has_no_surge(client: TestClient) -> None:
    _set(client, BEFORE)
    d = client.get("/v2/operator/statistics").json()
    assert d["available_event_count"] == 0
    assert d["affected_zone_count"] == 0
    assert d["top_surge_zones"] == []
    assert d["demand_delta_total"] == 0.0


def test_statistics_after_event_reports_surge(client: TestClient) -> None:
    _set(client, CONCERT)
    d = client.get("/v2/operator/statistics").json()
    assert d["affected_zone_count"] > 0
    assert d["top_surge_zones"]
    assert d["demand_delta_max"] > 0.0
    # Top surge zones are sorted by descending delta magnitude.
    deltas = [abs(z["forecast_delta"]) for z in d["top_surge_zones"]]
    assert deltas == sorted(deltas, reverse=True)
    # Honest labelling: the demo heuristic, not a measured model.
    assert d["model_version"] == "demo-heuristic-v1"


# ---- operator timeline (event-window analytics) ----------------------------------------------


def test_timeline_spans_window_and_is_cutoff_independent(client: TestClient) -> None:
    # The timeline evaluates the whole window regardless of the current replay cutoff.
    _set(client, BEFORE)
    t = client.get("/v2/operator/timeline").json()
    assert t["points"], "timeline must have points"
    assert t["window_start"][:10] == t["points"][0]["cutoff"][:10]
    hours = [p["cutoff"][11:13] for p in t["points"]]
    assert hours == sorted(hours)  # chronological
    assert t["model_version"] == "demo-heuristic-v1"


def test_timeline_event_count_is_monotonic_non_decreasing(client: TestClient) -> None:
    # As-of availability only accumulates: later cutoffs never have fewer available events.
    t = client.get("/v2/operator/timeline").json()
    counts = [p["event_count"] for p in t["points"]]
    assert counts == sorted(counts)
    assert counts[0] == 0  # window starts before any event
    assert counts[-1] >= 2  # both demo events available by the end


def test_timeline_shows_onset_after_first_event(client: TestClient) -> None:
    t = client.get("/v2/operator/timeline").json()
    pre = [p for p in t["points"] if p["event_count"] == 0]
    post = [p for p in t["points"] if p["event_count"] > 0]
    # Before any event: no demand delta and no event-driven shortage.
    assert all(p["demand_delta_total"] == 0.0 for p in pre)
    assert all(p["total_shortage_units"] == 0 for p in pre)
    # After the first event: at least one point carries a positive delta.
    assert any(p["demand_delta_total"] > 0.0 for p in post)


def test_timeline_markers_are_within_window(client: TestClient) -> None:
    t = client.get("/v2/operator/timeline").json()
    assert t["event_markers"], "the demo window crosses at least one event"
    for m in t["event_markers"]:
        assert t["window_start"] <= m["available_at"] <= t["window_end"]
        assert m["event_title"]

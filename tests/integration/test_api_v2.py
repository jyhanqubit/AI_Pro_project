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
    body = client.get("/v2/rider/stations/search", params={"k": 50}).json()
    stats = client.get("/v2/operator/statistics").json()
    assert body["count"] == stats["station_count"]  # returns the whole network
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
    # Availability counts partition the stations (multi-region network).
    assert sum(d["availability_counts"].values()) == d["station_count"]
    assert d["station_count"] >= 15
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


# ---- extra-bike allocation -------------------------------------------------------------------


def test_allocate_reduces_shortage_and_reports_benefit(client: TestClient) -> None:
    _set(client, CONCERT)
    r = client.post("/v2/operator/rebalancing/allocate", json={"extra_bikes": 6})
    assert r.status_code == 200
    d = r.json()
    assert d["extra_requested"] == 6
    assert d["placed"] <= 6
    assert d["placed"] == sum(s["added"] for s in d["stations"])
    # Every added bike removes one shortage unit (asymmetric objective, shortage_cost=3).
    assert d["shortage_units_after"] == d["shortage_units_before"] - d["placed"]
    assert d["shortage_reduction"] == d["placed"]
    assert d["benefit"] == round(d["cost_before"] - d["cost_after"], 4)
    assert d["benefit"] >= 0.0
    assert d["model_version"] == "demo-heuristic-v1"


def test_allocate_zero_is_a_no_op(client: TestClient) -> None:
    _set(client, CONCERT)
    d = client.post("/v2/operator/rebalancing/allocate", json={"extra_bikes": 0}).json()
    assert d["placed"] == 0
    assert d["shortage_units_after"] == d["shortage_units_before"]
    assert all(s["added"] == 0 for s in d["stations"])


def test_allocate_holds_back_surplus_bikes_honestly(client: TestClient) -> None:
    # Supplying far more than the network can use: only the total deficit is placed, the rest is
    # reported as leftover (held in depot) rather than force-placed into overflow.
    _set(client, CONCERT)
    d = client.post("/v2/operator/rebalancing/allocate", json={"extra_bikes": 500}).json()
    assert d["leftover"] > 0
    assert d["placed"] + d["leftover"] == 500
    assert d["shortage_units_after"] == 0
    assert d["overflow_units_after"] == d["overflow_units_before"]
    # Never exceed a station's dock capacity.
    for s in d["stations"]:
        assert s["bikes_after"] <= s["capacity"]


def test_allocate_respects_as_of_boundary(client: TestClient) -> None:
    # Before any event, targets are the normal-hour base, so there is little/no event shortage.
    _set(client, BEFORE)
    before = client.post("/v2/operator/rebalancing/allocate", json={"extra_bikes": 6}).json()
    # After the concert, event-raised targets create more shortage to relieve.
    _set(client, CONCERT)
    after = client.post("/v2/operator/rebalancing/allocate", json={"extra_bikes": 6}).json()
    assert after["shortage_units_before"] >= before["shortage_units_before"]


def test_allocate_cutoff_out_of_window_is_400(client: TestClient) -> None:
    r = client.post(
        "/v2/operator/rebalancing/allocate",
        json={"extra_bikes": 5, "cutoff": "2026-07-13T00:00:00-04:00"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error_code"] == "cutoff_out_of_window"


# ---- rider copilot (deterministic, grounded) -------------------------------------------------


def test_ask_status_is_grounded_in_search(client: TestClient) -> None:
    # The copilot's station numbers must match the search endpoint exactly (no fabrication).
    _set(client, CONCERT)
    ask = client.post("/v2/rider/ask", json={"query": "시청 자전거 있어?"}).json()
    assert ask["supported"] is True
    assert ask["intent"] == "status_at_location"
    assert ask["stations"], "a located status answer carries the station it describes"
    s = ask["stations"][0]
    hit = client.get("/v2/rider/stations/search", params={"q": "시청"}).json()["stations"][0]
    assert s["station_id"] == hit["station_id"]
    assert s["bikes"] == hit["bikes"]
    assert s["docks_free"] == hit["docks_free"]
    # The bike count is quoted verbatim in the answer text.
    assert f"{s['bikes']}대" in ask["answer"]


def test_ask_best_availability_lists_good_stations(client: TestClient) -> None:
    _set(client, CONCERT)
    ask = client.post("/v2/rider/ask", json={"query": "빌리기 좋은 곳 어디야"}).json()
    assert ask["intent"] == "best_availability"
    assert ask["stations"]
    assert all(s["level"] in ("plenty", "ok") for s in ask["stations"])


def test_ask_events_matches_available_events(client: TestClient) -> None:
    _set(client, CONCERT)
    ask = client.post("/v2/rider/ask", json={"query": "지금 무슨 일 있어?"}).json()
    events = client.get("/v1/events").json()["events"]
    assert ask["intent"] == "events"
    assert len(ask["events"]) == len(events)


def test_ask_unsupported_returns_clarification_not_fabrication(client: TestClient) -> None:
    _set(client, CONCERT)
    ask = client.post("/v2/rider/ask", json={"query": "날씨 어때?"}).json()
    assert ask["supported"] is False
    assert ask["intent"] == "unknown"
    assert ask["stations"] == []


def test_ask_is_deterministic(client: TestClient) -> None:
    _set(client, CONCERT)
    a = client.post("/v2/rider/ask", json={"query": "곧 부족한 곳 알려줘"}).json()
    b = client.post("/v2/rider/ask", json={"query": "곧 부족한 곳 알려줘"}).json()
    assert a["answer"] == b["answer"]
    assert [s["station_id"] for s in a["stations"]] == [s["station_id"] for s in b["stations"]]


def test_ask_empty_query_is_rejected(client: TestClient) -> None:
    r = client.post("/v2/rider/ask", json={"query": ""})
    assert r.status_code == 422  # Pydantic min_length


# ---- dynamic fare (V2-05, simulated shadow) --------------------------------------------------


def test_pricing_is_labelled_simulated_shadow(client: TestClient) -> None:
    _set(client, CONCERT)
    d = client.post("/v2/pricing/quote", json={}).json()
    assert d["is_simulated"] is True
    assert d["shadow"] is True
    assert "SIMULATED" in d["disclaimer"]
    assert d["quotes"]


def test_pricing_component_sum_and_cap(client: TestClient) -> None:
    _set(client, CONCERT)
    d = client.post("/v2/pricing/quote", json={}).json()
    for q in d["quotes"]:
        # base + surcharge reconciles with final price, and the multiplier is bounded.
        assert q["base_fare"] + q["scarcity_surcharge"] == pytest.approx(q["final_price"])
        assert q["tier_multiplier"] <= 1.50
        # A station is never both surcharged and credited.
        assert not (q["scarcity_surcharge"] > 0 and q["balancing_credit"] > 0)


def test_pricing_stale_scenario_falls_back_to_base(client: TestClient) -> None:
    _set(client, CONCERT)
    d = client.post("/v2/pricing/quote", json={"stale": True}).json()
    assert d["scenario"]["stale"] is True
    assert all(q["tier_multiplier"] == 1.0 for q in d["quotes"])
    assert all(q["scarcity_surcharge"] == 0.0 for q in d["quotes"])
    assert all(q["tier_reason"] == "stale" for q in d["quotes"])


def test_pricing_safety_scenario_blocks_surcharge(client: TestClient) -> None:
    _set(client, CONCERT)
    d = client.post("/v2/pricing/quote", json={"safety": True}).json()
    assert all(q["scarcity_surcharge"] == 0.0 for q in d["quotes"])
    assert all(q["guardrails"]["safety_block"] is True for q in d["quotes"])


def test_pricing_is_deterministic(client: TestClient) -> None:
    _set(client, CONCERT)
    a = client.post("/v2/pricing/quote", json={}).json()
    b = client.post("/v2/pricing/quote", json={}).json()
    assert [(q["station_id"], q["final_price"], q["quote_id"]) for q in a["quotes"]] == [
        (q["station_id"], q["final_price"], q["quote_id"]) for q in b["quotes"]
    ]


# ---- ops copilot (deterministic, artifact-grounded) ------------------------------------------


def test_ops_overview_facts_match_statistics(client: TestClient) -> None:
    _set(client, CONCERT)
    ask = client.post("/v2/operator/ask", json={"query": "지금 현황 어때?"}).json()
    stats = client.get("/v2/operator/statistics").json()
    assert ask["intent"] == "overview"
    assert ask["facts"]["system_utilization"] == stats["system_utilization"]
    assert ask["facts"]["stations_in_shortage"] == stats["stations_in_shortage"]
    assert ask["link"]["href"] == "/statistics"


def test_ops_shortage_facts_match(client: TestClient) -> None:
    _set(client, CONCERT)
    ask = client.post("/v2/operator/ask", json={"query": "부족한 곳 어디야"}).json()
    stats = client.get("/v2/operator/statistics").json()
    assert ask["facts"]["total_shortage_units"] == stats["total_shortage_units"]
    assert ask["link"]["href"] == "/rebalancing"


def test_ops_pricing_is_flagged_simulated(client: TestClient) -> None:
    _set(client, CONCERT)
    ask = client.post("/v2/operator/ask", json={"query": "요금 상태"}).json()
    assert ask["intent"] == "pricing"
    assert ask["facts"]["is_simulated"] is True
    assert "SIMULATED" in ask["answer"]
    assert ask["link"]["href"] == "/pricing"


def test_ops_navigate_returns_deeplink(client: TestClient) -> None:
    _set(client, CONCERT)
    ask = client.post("/v2/operator/ask", json={"query": "재배치 계획 열어"}).json()
    assert ask["intent"] == "navigate"
    assert ask["link"]["href"] == "/rebalancing"


def test_ops_unsupported_returns_clarification(client: TestClient) -> None:
    _set(client, CONCERT)
    ask = client.post("/v2/operator/ask", json={"query": "환율 알려줘"}).json()
    assert ask["supported"] is False
    assert ask["link"] is None


def test_ops_empty_query_is_rejected(client: TestClient) -> None:
    assert client.post("/v2/operator/ask", json={"query": ""}).status_code == 422


# ---- hybrid geo-semantic search (V2-03) ------------------------------------------------------


def test_hybrid_geo_query_ranks_nearest_and_hydrates_live(client: TestClient) -> None:
    _set(client, CONCERT)
    r = client.get(
        "/v2/rider/search/hybrid",
        params={"q": "City Hall 근처 자전거", "lat": 40.7377, "lng": -74.0324, "k": 3},
    ).json()
    assert r["provider"] == "local-hybrid"
    assert r["degraded"] is False
    stations = [x for x in r["results"] if x["kind"] == "station"]
    assert stations[0]["station"]["station_id"] == "JC_CITYHALL"
    assert stations[0]["distance_km"] == 0.0
    # Live inventory is hydrated from the operational store and matches the search endpoint.
    hit = client.get("/v2/rider/stations/search", params={"q": "시청"}).json()["stations"][0]
    assert stations[0]["station"]["bikes"] == hit["bikes"]


def test_hybrid_typo_resolves(client: TestClient) -> None:
    _set(client, CONCERT)
    r = client.get("/v2/rider/search/hybrid", params={"q": "호보켄터미널", "k": 2}).json()
    stations = [x for x in r["results"] if x["kind"] == "station"]
    assert stations[0]["station"]["station_id"] == "JC_HOBOKEN"


def test_hybrid_help_query_returns_help_doc(client: TestClient) -> None:
    _set(client, CONCERT)
    r = client.get("/v2/rider/search/hybrid", params={"q": "요금 할증 얼마", "k": 2}).json()
    assert any(x["kind"] == "help" and x["doc_id"] == "help_pricing" for x in r["results"])


# ---- predictive lift (V2-02) -----------------------------------------------------------------


def test_predictive_lift_is_honestly_blocked_offline(client: TestClient) -> None:
    d = client.get("/v2/model/predictive-lift").json()
    # The demo fixture cannot pass the coverage gate → claim disabled, honestly (no fabrication).
    assert d["coverage_ok"] is False
    assert d["verdict"] == "blocked_data"
    assert d["claim_enabled"] is False
    assert d["coverage"]["unique_events"] >= 1  # real measured coverage numbers

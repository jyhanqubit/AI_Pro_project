"""API integration tests (TestClient). CLAUDE.md sections 12, 13, 17.

Exercises the offline replay API: the as-of boundary through the HTTP layer (13:59 -> 14:00),
evidence-backed explanations (never evidence-free), scenario toggling, and the deferred
rebalancing endpoint. No network; the app is driven entirely by the news fixture.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api.app import create_app
from services.api.replay import reset_engine

BEFORE = "2026-07-12T13:59:00-04:00"  # transit event not yet available
AFTER = "2026-07-12T14:30:00-04:00"  # transit event available
CONCERT = "2026-07-12T15:30:00-04:00"  # concert also available


@pytest.fixture
def client() -> TestClient:
    reset_engine()  # drop singleton state so cutoff does not leak across tests
    return TestClient(create_app())


def _set(client: TestClient, cutoff: str) -> None:
    r = client.post("/v1/replay/set-cutoff", json={"cutoff": cutoff})
    assert r.status_code == 200


def test_health_reports_mode_and_versions(client: TestClient) -> None:
    body = client.get("/v1/health").json()
    assert body["status"] == "ok"
    assert body["mode"] == "historical_replay"
    assert body["model_version"] == "demo-heuristic-v1"
    assert body["feature_version"]


def test_as_of_boundary_through_api(client: TestClient) -> None:
    # Before the event is available: no events, every forecast delta is zero.
    _set(client, BEFORE)
    assert client.get("/v1/events").json()["events"] == []
    fc_before = client.get("/v1/forecasts").json()["forecasts"]
    assert fc_before and all(f["forecast_delta"] == 0.0 for f in fc_before)

    # After it becomes available: the event shows up and at least one zone moves.
    _set(client, AFTER)
    events = client.get("/v1/events").json()["events"]
    assert len(events) == 1
    fc_after = client.get("/v1/forecasts").json()["forecasts"]
    assert any(f["forecast_delta"] > 0.0 for f in fc_after)


def test_set_cutoff_out_of_window_is_400(client: TestClient) -> None:
    r = client.post("/v1/replay/set-cutoff", json={"cutoff": "2026-07-13T00:00:00-04:00"})
    assert r.status_code == 400
    assert r.json()["detail"]["error_code"] == "cutoff_out_of_window"


def test_explanation_is_evidence_backed(client: TestClient) -> None:
    _set(client, AFTER)
    zones = client.get("/v1/forecasts").json()["forecasts"]
    # Pick a zone that actually moved (has a driver).
    moved = next(f["zone_id"] for f in zones if f["forecast_delta"] > 0.0)
    ex = client.get(f"/v1/zones/{moved}/explanation").json()
    assert ex["drivers"], "a moved zone must have at least one driver"
    for d in ex["drivers"]:
        assert d["evidence_spans"], (
            "every driver must carry grounded evidence (never evidence-free)"
        )
        assert d["evidence_spans"][0]["text"]
        assert d["contributed_features"]  # concrete per-event feature attribution


def test_explanation_unknown_zone_is_404(client: TestClient) -> None:
    r = client.get("/v1/zones/deadbeef/explanation")
    assert r.status_code == 404
    assert r.json()["detail"]["error_code"] == "zone_not_found"


def test_scenario_toggle_reverts_event_effect(client: TestClient) -> None:
    _set(client, AFTER)
    events = client.get("/v1/events").json()["events"]
    event_id = events[0]["event_id"]
    body = {"cutoff": AFTER, "disabled_event_ids": [event_id]}
    zones = client.post("/v1/scenarios", json=body).json()["zones"]
    # Disabling the only event should pull the scenario forecast back to the baseline.
    for z in zones:
        assert z["scenario_forecast"] == pytest.approx(z["baseline_forecast"])


def test_rebalancing_returns_feasible_plan(client: TestClient) -> None:
    # Before the event: no zone shortage, so the plan is empty but still feasible.
    _set(client, BEFORE)
    before = client.post("/v1/rebalancing/solve", json={"cutoff": BEFORE, "method": "milp"}).json()
    assert before["feasible"] is True
    assert before["total_moved"] == 0
    assert before["shortage_units_after"] == 0

    # After the event: raised targets create a shortage that the solver relieves with real moves.
    after = client.post("/v1/rebalancing/solve", json={"cutoff": CONCERT, "method": "milp"}).json()
    assert after["feasible"] is True
    assert after["mode"] == "historical_replay"
    assert after["model_version"] == "demo-heuristic-v1"
    assert after["shortage_units_before"] > 0
    assert after["total_moved"] > 0
    assert after["shortage_reduction"] > 0
    assert after["shortage_units_after"] <= after["shortage_units_before"]
    # Every move is a concrete origin->destination relocation with a distance.
    assert after["moves"] and all(m["quantity"] > 0 for m in after["moves"])
    assert all(m["distance_km"] >= 0 for m in after["moves"])


def test_rebalancing_greedy_and_milp_both_feasible(client: TestClient) -> None:
    for method in ("greedy", "milp"):
        body = {"cutoff": CONCERT, "method": method}
        r = client.post("/v1/rebalancing/solve", json=body).json()
        assert r["feasible"] is True
        assert r["method"] == method


def test_rebalancing_cutoff_out_of_window_is_400(client: TestClient) -> None:
    r = client.post("/v1/rebalancing/solve", json={"cutoff": "2026-07-13T00:00:00-04:00"})
    assert r.status_code == 400
    assert r.json()["detail"]["error_code"] == "cutoff_out_of_window"

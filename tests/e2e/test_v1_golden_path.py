"""V1-09 golden-path E2E (offline, no internet). Walks the whole demo through the HTTP layer.

Exercises the v0 replay flow plus every V1 surface (recommendations, model lift + event-lift gate,
anomalies, news search/clusters, experiments) and asserts the honest properties: as-of leakage
boundary, simulated/pending/blocked claim states, and no fabricated lift. Endpoints gated on
optional extras (torch/faiss) may return 503; the test checks the honest fields when 200.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api.app import create_app
from services.api.replay import reset_engine

BEFORE = "2026-07-12T13:59:00-04:00"
CONCERT = "2026-07-12T15:30:00-04:00"


@pytest.fixture
def client() -> TestClient:
    reset_engine()
    return TestClient(create_app())


def test_golden_path_offline(client: TestClient) -> None:
    # 1. Health + replay clock.
    assert client.get("/v1/health").json()["mode"] == "historical_replay"

    # 2. As-of boundary: no events at 13:59, events after the concert cutoff.
    client.post("/v1/replay/set-cutoff", json={"cutoff": BEFORE})
    assert client.get("/v1/events").json()["events"] == []
    client.post("/v1/replay/set-cutoff", json={"cutoff": CONCERT})
    events = client.get("/v1/events").json()["events"]
    assert len(events) >= 2

    # 3. Forecasts + evidence-backed explanation.
    fc = client.get("/v1/forecasts").json()
    assert fc["forecasts"] and fc["model_version"] == "demo-heuristic-v1"
    zone = fc["forecasts"][0]["zone_id"]
    ex = client.get(f"/v1/zones/{zone}/explanation").json()
    assert ex["drivers"] and all(d["evidence_spans"] for d in ex["drivers"])  # never evidence-free

    # 4. Scenario + feasible rebalancing (the Act step).
    sc = client.post("/v1/scenarios", json={"cutoff": CONCERT, "disabled_event_ids": []}).json()
    assert sc["zones"]
    reb = client.post("/v1/rebalancing/solve", json={"cutoff": CONCERT, "method": "milp"}).json()
    assert reb["feasible"] is True and reb["total_moved"] > 0

    # 5. Recommendation (simulated; may 503 without the recsys extra).
    r = client.post(
        "/v1/recommendations/stations", json={"mode": "rent", "lat": 40.7196, "lng": -74.0431}
    )
    if r.status_code == 200:
        d = r.json()
        assert d["claim_state"] == "simulated" and d["operating_mode"] == "policy_simulation"

    # 6. Model lift + event-lift gate: measured B0-B4, event lift honestly blocked.
    ml = client.get("/v1/model/lift").json()
    assert ml["event_lift_verdict"] == "insufficient_event_overlap"
    assert ml["gate"]["gate_passed"] is False and ml["gate"]["claim_enabled"] is False

    # 7. Anomalies: synthetic faults detected + a depletion explained by an event.
    an = client.get("/v1/anomalies").json()
    assert an["n_alerts"] >= 4
    assert an["by_root_cause"].get("explained_by_event", 0) >= 1
    assert an["synthetic_fault_count"] == an["n_alerts"]  # all flagged synthetic

    # 8. News vector search + same-event clusters (may 503 without faiss).
    ns = client.get("/v1/news/search", params={"q": "PATH suspended Hoboken"})
    if ns.status_code == 200:
        assert ns.json()["results"]
        cl = client.get("/v1/news/clusters").json()
        assert any(c["size"] >= 3 for c in cl["clusters"])  # the PATH wire copies group

    # 9. Experiments: A/A validation passes; results are simulated.
    ex2 = client.get("/v1/experiments/switchback").json()
    assert ex2["is_simulated"] is True and ex2["aa_validation_passed"] is True

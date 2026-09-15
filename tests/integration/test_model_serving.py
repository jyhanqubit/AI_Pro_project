"""V2-07 promoted-model serving endpoint. CLAUDE.md §12, §22.

With the committed artifacts present the endpoint must run a genuine ``estimator.predict`` and
return provenance-carrying forecasts; with them absent it must answer 503 (honest degrade), never
a demo-heuristic fallback.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api import model_serving
from services.api.app import create_app

_ARTIFACTS = (
    Path("reports/v2/holdout/promoted_model.joblib"),
    Path("reports/v2/holdout/serving_features.json"),
)
_have_artifacts = all(p.exists() for p in _ARTIFACTS)


@pytest.fixture()
def client():
    model_serving._load.cache_clear()
    yield TestClient(create_app())
    model_serving._load.cache_clear()


@pytest.mark.skipif(not _have_artifacts, reason="run `make v2-holdout` + `make v2-serving-export`")
def test_model_forecast_serves_measured_predictions(client) -> None:
    r = client.get("/v2/model/forecast?top=5")
    assert r.status_code == 200
    body = r.json()
    # provenance the serving contract requires (V2-01 manifest fields)
    assert body["claim_status"] == "measured"
    assert body["run_id"].startswith("run_")
    assert body["model"]["algorithm"] == "hist_gradient_boosting"
    assert body["forecast_horizon_h"] == 1
    # genuine per-zone predictions, ranked descending
    fx = body["forecasts"]
    assert 1 <= len(fx) <= 5
    vals = [f["predicted_departures"] for f in fx]
    assert vals == sorted(vals, reverse=True)
    assert all(isinstance(f["zone_id"], str) and f["zone_id"] for f in fx)
    # the serving hour is strictly after the training boundary (out-of-sample)
    assert body["serving_hour"] > body["model"]["trained_through_hour"]


@pytest.mark.skipif(not _have_artifacts, reason="run `make v2-holdout` + `make v2-serving-export`")
def test_top_param_bounds_the_result(client) -> None:
    r = client.get("/v2/model/forecast?top=1")
    assert r.status_code == 200
    assert len(r.json()["forecasts"]) == 1


def test_missing_artifacts_answer_503(client, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(model_serving, "_HOLDOUT_DIR", tmp_path)
    monkeypatch.setattr(model_serving, "_SERVING_PATH", tmp_path / "serving_features.json")
    monkeypatch.setattr(model_serving, "_REPORT_PATH", tmp_path / "h3_multiholdout.json")
    r = client.get("/v2/model/forecast")
    assert r.status_code == 503
    assert r.json()["detail"]["error_code"] == "promoted_model_unavailable"

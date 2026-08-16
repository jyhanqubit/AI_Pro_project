"""Serve the promoted measured forecasting model over the API (V2-07).

Loads the promoted-model bundle (``reports/v2/holdout/promoted_model.joblib``) and the committed
serving feature snapshot (``serving_features.json``), and returns genuine next-hour predictions —
``estimator.predict`` runs on every request, no precomputed answers. Every response carries the
manifest provenance (``run_id`` / ``claim_status`` / ``freshness``) plus the holdout WAPE so a
served number stays traceable to its measured origin.

Honest degrade: if the fitted model or the feature snapshot is absent the endpoint returns 503 with
the regeneration command — it never falls back to the demo heuristic under this route.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from ml.forecasting.promoted import PromotedModel, PromotedModelUnavailable, load_promoted_model

_HOLDOUT_DIR = Path("reports/v2/holdout")
_SERVING_PATH = _HOLDOUT_DIR / "serving_features.json"
_REPORT_PATH = _HOLDOUT_DIR / "h3_multiholdout.json"


class ServingUnavailable(RuntimeError):
    """Raised when the model or its serving features cannot be loaded (route answers 503)."""


@lru_cache(maxsize=1)
def _load() -> tuple[PromotedModel, dict[str, Any], dict[str, Any]]:
    try:
        model = load_promoted_model(_HOLDOUT_DIR)
    except PromotedModelUnavailable as exc:
        raise ServingUnavailable(str(exc)) from exc
    if not model.is_servable:
        raise ServingUnavailable(
            "promoted_model.joblib missing — run `make v2-holdout` to fit and persist the model."
        )
    if not _SERVING_PATH.exists():
        raise ServingUnavailable(
            f"{_SERVING_PATH} missing — run `make v2-serving-export` to build serving features."
        )
    snapshot = json.loads(_SERVING_PATH.read_text(encoding="utf-8"))
    holdout: dict[str, Any] = {}
    if _REPORT_PATH.exists():
        holdout = json.loads(_REPORT_PATH.read_text(encoding="utf-8")).get("aggregate", {})
    return model, snapshot, holdout


def model_forecast(top: int = 20) -> dict[str, Any]:
    """Next-hour departures prediction per H3 zone from the promoted measured model."""
    model, snapshot, holdout = _load()
    zones = snapshot["zones"]

    matrix = np.array(
        [
            [
                np.nan if z["features"].get(name) is None else float(z["features"][name])
                for name in model.features
            ]
            for z in zones
        ],
        dtype=float,
    )
    preds = model.estimator.predict(matrix)

    ranked = sorted(
        (
            {
                "zone_id": z["zone_id"],
                "lat": z["lat"],
                "lng": z["lng"],
                "predicted_departures": round(float(p), 2),
            }
            for z, p in zip(zones, preds, strict=True)
        ),
        key=lambda r: r["predicted_departures"],
        reverse=True,
    )

    return {
        "mode": "historical_replay",
        "claim_status": model.claim_status,
        "run_id": model.run_id,
        "freshness": model.freshness,
        "model": {
            "algorithm": model.manifest.get("algorithm"),
            "params": model.manifest.get("params"),
            "feature_version": model.manifest.get("feature_version"),
            "target": model.target,
            "trained_on_rows": model.manifest.get("trained_on_rows"),
            "trained_through_hour": model.manifest.get("trained_through_hour"),
            "holdout_wape_mean": (holdout.get("wape") or {}).get("mean"),
            "holdout_mase_mean": (holdout.get("mase") or {}).get("mean"),
        },
        "serving_hour": snapshot["serving_hour"],
        "forecast_horizon_h": 1,
        "n_zones": len(zones),
        "forecasts": ranked[: max(1, top)],
        "note": (
            "승격된 측정 모델(hist_gradient_boosting)이 요청 시점에 실제로 예측한 다음 1시간 "
            "departures입니다. 피처는 학습 데이터 마지막 시각까지의 실측 이력에서 누수 없이 계산된 "
            "값이며(§5.4), 데모 휴리스틱과 무관합니다. 음수 예측은 그대로 보고합니다."
        ),
    }

"""Model registry + event-lift surfacing (V1_Prompt §9, §10).

Wraps the measured Phase-06 ablation into an M0 / M1 / M1-zero view:

    M0 baseline      = B1 (demand history + calendar)
    M1 event-aware   = B4 (B1 + LLM event + graph-spatial features)
    M1-zero          = B1 with event features zeroed (== B1 on data with no event overlap)

The **model-attributed event lift** is M0's error minus M1's error. On the current data it is
exactly 0 because the curated events postdate the evaluation window (event features are all zero,
verified), so the lift is reported as ``insufficient_event_overlap`` — never fabricated (§10).
Collecting overlapping news (`make v1-collect-news-live`) unlocks a real measurement (V1-04).
"""

from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_RESULTS = _ROOT / "reports" / "phase06_results.json"

_ARM_LABELS = {
    "B0": "Seasonal Naive",
    "B1": "History + Calendar  (M0 baseline)",
    "B2": "+ Raw news volume",
    "B3": "+ LLM event features",
    "B4": "+ Graph-spatial features  (M1 event-aware)",
}


class RegistryUnavailable(RuntimeError):
    """Raised when the measured Phase-06 results artifact is missing."""


def _load() -> dict:
    if not _RESULTS.exists():
        raise RegistryUnavailable(
            "reports/phase06_results.json missing — run `make evaluate` to produce it."
        )
    return json.loads(_RESULTS.read_text(encoding="utf-8"))


def event_lift_summary() -> dict:
    """Structured M0/M1 lift for the API / Model Lift Lab (measured; never fabricated)."""
    d = _load()
    ablation = d["ablation"]

    def m(arm: str) -> dict:
        a = ablation[arm]
        return {"wape": a["wape"], "mae": a["mae"], "mase": a["mase"]}

    arms = [
        {"arm": k, "label": _ARM_LABELS.get(k, k), **m(k)}
        for k in ("B0", "B1", "B2", "B3", "B4")
        if k in ablation
    ]
    m0, m1 = m("B1"), m("B4")
    lift = round(m0["wape"] - m1["wape"], 6)  # >0 would mean M1 lowers WAPE
    verified = d.get("event_feature_verification", {})
    event_zero = bool(verified.get("event_features_zero", True))

    return {
        "model_version": d.get("best_algorithm", "unknown"),
        "feature_version": "gfv1",
        "target": d.get("target", "departures"),
        "n_test": d.get("n_test"),
        "test_window_hours": d.get("test_window_hours"),
        "seasonal_scale_mae": d.get("seasonal_scale_mae"),
        "ablation": arms,
        "m0_baseline": m0,
        "m1_event_aware": m1,
        "model_attributed_wape_lift": lift,
        "delta_stability": d.get("delta_stability_b4_vs_b1", {}),
        "event_lift_verdict": "insufficient_event_overlap" if event_zero else "measured",
        "event_verification": verified,
        "claim_state": "measured",  # the metrics are measured; the *event* lift is gated below
        "note": (
            "B1(과거+달력)이 B0(계절 naive)보다 크게 낮은 오차를 보이지만, "
            "B2~B4(뉴스·이벤트·그래프)는 B1과 동일합니다. 큐레이션된 이벤트가 6월 평가창 "
            "이후(7/12)라 이벤트 피처가 전부 0이기 때문입니다(검증됨). 따라서 '이벤트 lift'는 "
            "아직 측정 불가(insufficient_event_overlap)이며, 겹치는 6월 뉴스를 수집"
            "(make v1-collect-news-live)해 재학습하면 V1-04에서 실제로 측정됩니다."
        ),
    }

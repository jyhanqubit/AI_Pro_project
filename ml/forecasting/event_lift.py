"""Event-lift evaluation + claim gate (V1_Prompt §10).

Formalises "do news/graph features reduce holdout error?" as a paired B1(M0) vs B4(M1) comparison
with an uncertainty interval, and checks the claim gate from config/v1/claims.yaml. On the current
data B4 == B1 exactly (event features are all zero — no overlap), so the paired difference is 0
with a [0, 0] interval and the gate **fails** on `nonzero_test_event_features` (+ real news).
The lift claim therefore stays disabled — never fabricated (§10, invariant 6/15).
"""

from __future__ import annotations

from .registry import _load


def event_lift_gate() -> dict:
    d = _load()
    ablation = d["ablation"]
    b1, b4 = ablation["B1"], ablation["B4"]
    stability = d.get("delta_stability_b4_vs_b1", {"mean_abs_delta": 0.0, "std_delta": 0.0})
    verified = d.get("event_feature_verification", {})
    event_zero = bool(verified.get("event_features_zero", True))

    # Paired B4 - B1 comparison (WAPE). B4 == B1 -> difference 0; the stability stats confirm the
    # per-zone-hour paired differences are all 0, so a bootstrap CI is degenerate at [0, 0].
    paired_wape_diff = round(b1["wape"] - b4["wape"], 6)
    ci = [0.0, 0.0] if stability.get("std_delta", 0.0) == 0.0 else None

    conditions = {
        "nonzero_test_event_features": not event_zero,
        "same_split_and_target": True,  # one ablation, same learner/split/target
        "real_historical_news": False,  # curated fixture, not real GDELT (see V1-01 BLOCKED_DATA)
        "real_demand_labels": True,  # real June Citi Bike trips
        "paired_comparison": True,  # paired B4 vs B1 above
        "uncertainty_interval": ci is not None,
    }
    passed = all(conditions.values())
    return {
        "target": d.get("target", "departures"),
        "paired_wape_diff_m0_minus_m1": paired_wape_diff,  # >0 would mean M1 helps
        "paired_ci": ci,
        "delta_stability": stability,
        "gate_conditions": conditions,
        "gate_passed": passed,
        "verdict": "measured_lift" if passed else "insufficient_event_overlap",
        "claim_enabled": passed,
        "note": (
            "게이트 미통과 → 이벤트 lift 주장 비활성. 실패 조건: 테스트 이벤트 피처 비영(현재 0), "
            "실제 과거 뉴스(현재 fixture). 겹치는 실뉴스 수집 후 재학습 시 통과 가능(V1-01/V1-04)."
        ),
    }

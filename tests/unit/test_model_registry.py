"""V1-03 model registry / event-lift surfacing tests (V1_Prompt §9, §10)."""

from __future__ import annotations

from ml.forecasting.registry import event_lift_summary


def test_event_lift_summary_shape_and_arms() -> None:
    s = event_lift_summary()
    arms = {a["arm"] for a in s["ablation"]}
    assert {"B0", "B1", "B2", "B3", "B4"} <= arms
    assert s["model_version"]  # e.g. "knn"
    for a in s["ablation"]:
        assert a["wape"] >= 0 and a["mae"] >= 0 and a["mase"] >= 0


def test_m0_beats_seasonal_naive() -> None:
    s = event_lift_summary()
    b0 = next(a for a in s["ablation"] if a["arm"] == "B0")
    assert s["m0_baseline"]["wape"] < b0["wape"]  # history+calendar improves on seasonal naive


def test_event_lift_is_honestly_zero_and_flagged() -> None:
    s = event_lift_summary()
    # On data with no event overlap, B2..B4 == B1 and the lift is exactly zero, flagged as such.
    assert s["model_attributed_wape_lift"] == 0.0
    assert s["event_lift_verdict"] == "insufficient_event_overlap"
    assert s["event_verification"]["event_features_zero"] is True
    b1 = next(a for a in s["ablation"] if a["arm"] == "B1")
    b4 = next(a for a in s["ablation"] if a["arm"] == "B4")
    assert b1["wape"] == b4["wape"]  # no fabricated improvement

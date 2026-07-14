"""V1-04 event-lift gate tests (V1_Prompt §10 acceptance)."""

from __future__ import annotations

from ml.forecasting.event_lift import event_lift_gate


def test_gate_blocks_on_zero_event_overlap() -> None:
    g = event_lift_gate()
    # B4 == B1 on this data -> paired difference is exactly 0 with a degenerate [0,0] interval.
    assert g["paired_wape_diff_m0_minus_m1"] == 0.0
    assert g["paired_ci"] == [0.0, 0.0]
    # The gate must fail (no fabricated lift) and disable the claim.
    assert g["gate_passed"] is False
    assert g["claim_enabled"] is False
    assert g["verdict"] == "insufficient_event_overlap"


def test_gate_reports_which_conditions_fail() -> None:
    c = event_lift_gate()["gate_conditions"]
    assert c["nonzero_test_event_features"] is False  # events don't overlap the eval window
    assert c["real_historical_news"] is False  # curated fixture, not real GDELT
    # ...but the honest parts still hold:
    assert c["real_demand_labels"] is True
    assert c["paired_comparison"] is True
    assert c["uncertainty_interval"] is True

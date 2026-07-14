"""V1-07D dynamic incentive & policy-simulation tests (V1_Prompt §16 acceptance)."""

from __future__ import annotations

import pytest

from config.pricing import CREDIT_TIERS, POLICIES, PricingConfig
from ml.pricing.policies import run_policy
from ml.pricing.scenario import build_demo_scenario
from ml.pricing.simulator import ChoiceSimulator


@pytest.fixture
def stations():
    return build_demo_scenario()


def test_credit_tiers_are_non_negative_and_expected() -> None:
    assert CREDIT_TIERS == (0.0, 0.5, 1.0, 1.5, 2.0, 3.0)
    assert all(c >= 0 for c in CREDIT_TIERS)  # no surcharge (§16)


def test_simulator_rejects_negative_credit(stations) -> None:
    with pytest.raises(ValueError, match="no surcharge"):
        ChoiceSimulator().run(stations, credits={stations[0].station_id: -1.0})


def test_simulator_is_deterministic(stations) -> None:
    a = ChoiceSimulator(PricingConfig(seed=7)).run(stations)
    b = ChoiceSimulator(PricingConfig(seed=7)).run(stations)
    assert a.fulfilled == b.fulfilled
    assert a.shortage_events == b.shortage_events
    assert a.total_detour_km == b.total_detour_km


def test_all_results_are_simulated_with_disclaimer(stations) -> None:
    for spec in POLICIES:
        r = run_policy(spec, stations)
        assert r.is_simulated is True
        assert "SIMULATED OUTCOME" in r.disclaimer


def test_budget_is_a_hard_cap(stations) -> None:
    cfg = PricingConfig(incentive_budget=5.0)
    # Dynamic-credit policy must never spend beyond the budget.
    for spec in POLICIES:
        r = run_policy(spec, stations, cfg)
        assert r.incentive_spend <= cfg.incentive_budget + 1e-9


def test_p0_has_shortage_and_a_credit_or_truck_policy_reduces_it(stations) -> None:
    results = {spec.key: run_policy(spec, stations) for spec in POLICIES}
    # No-action baseline leaves unmet demand.
    assert results["P0"].shortage_minutes > 0
    # At least one active policy fulfils more demand than doing nothing.
    assert any(
        results[k].fulfilled_demand_rate > results["P0"].fulfilled_demand_rate
        for k in ("P1", "P3", "P5")
    )


def test_fairness_disparity_is_measured(stations) -> None:
    r = run_policy(POLICIES[0], stations)  # P0
    assert 0.0 <= r.service_disparity <= 1.0


def test_truck_only_uses_no_incentive_and_moves_bikes(stations) -> None:
    r = run_policy(POLICIES[1], stations)  # P1 truck only
    assert r.incentive_spend == 0.0
    assert r.truck_bike_km > 0.0

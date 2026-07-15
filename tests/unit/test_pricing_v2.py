"""Dynamic-fare kernel (V2-05). CLAUDE.md §14, §22 + V2 invariants.

The kernel is a pure, deterministic function; these tests pin the guardrails that make the surcharge
safe to expose: component-sum auditability, the hard multiplier cap, base-fare fallback on stale /
safety, credit-only-when-surplus, and determinism. Pricing depends solely on scarcity — no rider
attribute is ever an input to this function.
"""

from __future__ import annotations

from config.pricing_v2 import DynamicFareConfig
from ml.pricing.dynamic import price_quote, scarcity_pressure_score, select_tier

CFG = DynamicFareConfig()


def _q(**kw):
    base = dict(
        bikes=0,
        target=10,
        capacity=20,
        surplus=0,
        demand_delta=0.0,
        neighbor_spare=0.0,
        stale=False,
        safety_block=False,
        cfg=CFG,
    )
    base.update(kw)
    return price_quote(**base)


def test_component_sum_equals_final_price() -> None:
    # base_fare + scarcity_surcharge must reconcile with final_price exactly (auditable).
    for delta in (0.0, 2.0, 6.0, 20.0):
        q = _q(bikes=1, target=12, demand_delta=delta)
        assert q.base_fare + q.scarcity_surcharge == q.final_price


def test_surcharge_never_exceeds_cap() -> None:
    # Even at maximum pressure the multiplier is bounded by max_multiplier.
    q = _q(bikes=0, target=20, capacity=20, demand_delta=100.0)
    assert q.tier_multiplier <= CFG.max_multiplier
    assert q.final_price <= CFG.base_fare * CFG.max_multiplier


def test_stale_data_falls_back_to_base() -> None:
    q = _q(bikes=0, target=20, demand_delta=50.0, stale=True)
    assert q.tier_multiplier == 1.0
    assert q.scarcity_surcharge == 0.0
    assert q.tier_reason == "stale"


def test_safety_event_blocks_surcharge() -> None:
    q = _q(bikes=0, target=20, demand_delta=50.0, safety_block=True)
    assert q.tier_multiplier == 1.0
    assert q.scarcity_surcharge == 0.0
    assert q.tier_reason == "safety_no_surcharge"


def test_credit_only_at_surplus_and_no_surcharge() -> None:
    # A surplus station gets a pickup credit and never a surcharge.
    q = _q(bikes=18, target=10, surplus=8)
    assert q.tier_multiplier == 1.0
    assert q.scarcity_surcharge == 0.0
    assert q.balancing_credit > 0.0
    # A scarce station gets a surcharge and no credit.
    scarce = _q(bikes=1, target=12, capacity=14, demand_delta=6.0)
    assert scarce.scarcity_surcharge > 0.0
    assert scarce.balancing_credit == 0.0


def test_neighbor_surplus_reduces_pressure() -> None:
    hot = _q(bikes=2, target=12, demand_delta=4.0, neighbor_spare=0.0)
    relieved = _q(bikes=2, target=12, demand_delta=4.0, neighbor_spare=24.0)
    assert relieved.scarcity_score <= hot.scarcity_score


def test_tiers_are_monotonic_in_score() -> None:
    prev = 0.0
    for score in (0.0, 0.2, 0.5, 0.9):
        tier = select_tier(score, CFG)
        assert tier >= prev
        prev = tier
    assert select_tier(0.0, CFG) == CFG.tiers[0]
    assert select_tier(1.0, CFG) == CFG.tiers[-1]


def test_is_deterministic() -> None:
    a = _q(bikes=3, target=12, demand_delta=3.0, neighbor_spare=5.0)
    b = _q(bikes=3, target=12, demand_delta=3.0, neighbor_spare=5.0)
    assert a == b


def test_score_is_bounded_unit_interval() -> None:
    from ml.pricing.dynamic import scarcity_components

    c = scarcity_components(
        bikes=0, target=20, capacity=20, demand_delta=100.0, neighbor_spare=0.0, cfg=CFG
    )
    assert 0.0 <= scarcity_pressure_score(c, CFG) <= 1.0

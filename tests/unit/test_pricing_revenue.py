"""Simulated dynamic-fare revenue kernel (V2-05). CLAUDE.md §14, §22.

Pins the honest accounting of the revenue simulation: the elasticity conversion curve, the supply
(bike) cap on rentals, that a flat re-price of the same stations is the counterfactual, and the
central claim — a bounded surcharge at a supply-constrained station raises revenue without losing a
rental, and that uplift survives the modeled conversion loss. Pure functions; no engine, no I/O.
"""

from __future__ import annotations

import pytest

from config.pricing_v2 import DynamicFareConfig
from ml.pricing.dynamic import price_quote
from ml.pricing.revenue import (
    StationDemand,
    compare_revenue,
    conversion_factor,
    elasticity_sweep,
)

CFG = DynamicFareConfig()


def _quote(bikes: int, target: int, demand_delta: float):
    return price_quote(
        bikes=bikes,
        target=target,
        capacity=max(target, bikes) * 2,
        surplus=max(0, bikes - target),
        demand_delta=demand_delta,
        neighbor_spare=0.0,
        stale=False,
        safety_block=False,
        cfg=CFG,
    )


def test_conversion_factor_is_monotone_and_bounded() -> None:
    assert conversion_factor(1.0, 0.5) == 1.0  # base fare never sheds demand
    assert conversion_factor(1.5, 0.0) == 1.0  # perfectly inelastic: no drop
    # Higher multiplier and higher elasticity both reduce conversion, clamped to [0, 1].
    assert conversion_factor(1.5, 0.5) == pytest.approx(0.75)
    assert conversion_factor(2.0, 1.0) == 0.0
    assert conversion_factor(3.0, 1.0) == 0.0  # clamped, never negative


def test_conversion_factor_rejects_negative_elasticity() -> None:
    with pytest.raises(ValueError):
        conversion_factor(1.5, -0.1)


def test_flat_counterfactual_prices_at_base_fare() -> None:
    # A scarce station (bikes below target, event delta) surcharges under dynamic; flat re-prices
    # the identical station at the base fare.
    d = StationDemand("S", "z", base_demand=10, available_bikes=6)
    q = _quote(bikes=6, target=12, demand_delta=5.0)
    assert q.tier_multiplier > 1.0  # dynamic surcharges this scarce station
    cmp = compare_revenue([(d, q)], elasticity=0.5)
    assert cmp.flat.stations[0].multiplier == 1.0
    assert cmp.flat.stations[0].final_price == q.base_fare
    assert cmp.dynamic.stations[0].final_price == q.final_price


def test_supply_constrained_surcharge_raises_revenue_without_losing_rentals() -> None:
    # Demand (10) far exceeds available bikes (3): even after the conversion drop demand > supply,
    # so the surcharge is pure upside — same rentals, more revenue.
    d = StationDemand("S", "z", base_demand=10, available_bikes=3)
    q = _quote(bikes=3, target=14, demand_delta=8.0)
    assert q.tier_multiplier > 1.0
    cmp = compare_revenue([(d, q)], elasticity=0.5)
    assert cmp.fulfilled_delta == 0  # no rental lost
    assert cmp.dynamic.total_fulfilled == 3  # bike-capped
    assert cmp.revenue_uplift > 0.0  # revenue strictly higher
    assert cmp.dynamic.total_revenue == pytest.approx(3 * q.final_price)


def test_uplift_is_robust_across_elasticity_when_supply_constrained() -> None:
    # Demand (40) hugely exceeds supply (4): even a max surcharge at max elasticity keeps converted
    # demand above the few bikes.
    d = StationDemand("S", "z", base_demand=40, available_bikes=4)
    q = _quote(bikes=4, target=16, demand_delta=8.0)
    sweep = elasticity_sweep([(d, q)], elasticities=(0.0, 0.5, 1.0, 1.5))
    # Strongly supply-constrained: the surcharge never pushes converted demand below supply, so the
    # uplift stays positive at every elasticity (the honest "why it holds" check).
    assert all(c.revenue_uplift > 0.0 for c in sweep)
    assert all(c.fulfilled_delta == 0 for c in sweep)


def test_high_elasticity_can_erase_the_uplift_when_not_supply_constrained() -> None:
    # Demand barely above supply: a high enough elasticity drops converted demand below the bikes,
    # so the surcharge now loses rentals and the uplift can vanish or go negative — reported, never
    # hidden.
    d = StationDemand("S", "z", base_demand=7, available_bikes=6)
    q = _quote(bikes=6, target=14, demand_delta=8.0)
    low = compare_revenue([(d, q)], elasticity=0.0)
    high = compare_revenue([(d, q)], elasticity=1.5)
    assert low.revenue_uplift > 0.0
    assert high.fulfilled_delta < 0  # the surcharge sheds a rental at high elasticity
    assert high.revenue_uplift <= low.revenue_uplift


def test_surplus_station_is_untouched_by_pricing() -> None:
    # A well-stocked station gets no surcharge, so flat and dynamic revenue are identical there.
    d = StationDemand("S", "z", base_demand=5, available_bikes=20)
    q = _quote(bikes=20, target=6, demand_delta=0.0)
    assert q.tier_multiplier == 1.0
    cmp = compare_revenue([(d, q)], elasticity=0.5)
    assert cmp.revenue_uplift == 0.0
    assert cmp.fulfilled_delta == 0

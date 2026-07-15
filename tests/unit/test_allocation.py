"""Unit tests for new-supply allocation. CLAUDE.md sections 14.1, 17.

Covers the "add m new bikes for maximum benefit" solver: it fills deficits first, is optimal vs
brute-force enumeration, never places a net-negative bike unless asked, respects dock capacity,
and reports benefit honestly (including the do-nothing m=0 case).
"""

from __future__ import annotations

from itertools import product

import pytest

from config.rebalancing import RebalancingCosts
from optimization.classical.allocation import allocate_supply
from optimization.classical.objective import imbalance_units
from optimization.classical.problem import RebalancingProblem, Station


def _problem() -> RebalancingProblem:
    # Three deficit stations (need 7+5+4 = 16) and one already-at-target station.
    stations = (
        Station("HOB", "Hoboken", 40.7360, -74.0301, bikes=2, capacity=20, target=9, zone_id="z1"),
        Station("CTH", "Hall", 40.7377, -74.0324, bikes=3, capacity=18, target=8, zone_id="z2"),
        Station("NEW", "Newport", 40.7272, -74.0337, bikes=4, capacity=16, target=8, zone_id="z3"),
        Station("GRV", "Grove", 40.7196, -74.0431, bikes=6, capacity=20, target=6, zone_id="z4"),
    )
    return RebalancingProblem(stations=stations, costs=RebalancingCosts())


def _total_deficit(p: RebalancingProblem) -> int:
    return sum(s.deficit for s in p.stations)


def _brute_force_best_benefit(p: RebalancingProblem, m: int, *, place_all: bool) -> float:
    """Max benefit of placing exactly m (place_all) or up to m (else), by brute force."""
    c = p.costs
    before = imbalance_units(p, {s.station_id: s.bikes for s in p.stations})
    baseline = c.shortage_cost * before[0] + c.overflow_cost * before[1]
    rooms = [s.dock_room for s in p.stations]
    best = float("-inf")
    for adds in product(*[range(r + 1) for r in rooms]):
        placed = sum(adds)
        if place_all and placed != m:
            continue
        if not place_all and placed > m:
            continue
        final = {s.station_id: s.bikes + a for s, a in zip(p.stations, adds, strict=True)}
        after = imbalance_units(p, final)
        cost = c.shortage_cost * after[0] + c.overflow_cost * after[1]
        best = max(best, baseline - cost)
    return best


def test_zero_extra_is_do_nothing() -> None:
    p = _problem()
    plan = allocate_supply(p, 0)
    assert plan.allocated == 0
    assert plan.held == 0
    assert plan.benefit == 0.0
    assert plan.allocations == ()


def test_fills_deficits_and_is_optimal() -> None:
    p = _problem()
    d = _total_deficit(p)
    # Fewer than total deficit: every bike removes one shortage unit -> benefit = m*shortage_cost.
    for m in (1, 5, d):
        plan = allocate_supply(p, m)
        assert plan.to_deficit == m
        assert plan.surplus_placed == 0
        assert plan.held == 0
        assert plan.benefit == pytest.approx(m * p.costs.shortage_cost)
        assert plan.benefit == pytest.approx(_brute_force_best_benefit(p, m, place_all=False))


def test_surplus_bikes_are_held_by_default() -> None:
    p = _problem()
    d = _total_deficit(p)
    plan = allocate_supply(p, d + 5)  # 5 more than needed
    assert plan.to_deficit == d
    assert plan.surplus_placed == 0
    assert plan.held == 5
    assert plan.shortage_after == 0
    # Holding the surplus is the true benefit-maximising choice (place_all=False oracle).
    assert plan.benefit == pytest.approx(_brute_force_best_benefit(p, d + 5, place_all=False))


def test_place_surplus_deploys_all_and_reports_negative_marginal() -> None:
    p = _problem()
    d = _total_deficit(p)
    m = d + 5
    plan = allocate_supply(p, m, place_surplus=True)
    assert plan.to_deficit == d
    assert plan.surplus_placed == 5
    assert plan.held == 0
    assert plan.allocated == m
    # Deploying all m is exactly the enumerated optimum for "place exactly m".
    assert plan.benefit == pytest.approx(_brute_force_best_benefit(p, m, place_all=True))
    # Surplus bikes cost overflow: benefit is deficit gain minus the 5 overflow units.
    expected = d * p.costs.shortage_cost - 5 * p.costs.overflow_cost
    assert plan.benefit == pytest.approx(expected)


def test_held_when_no_dock_room_left() -> None:
    # One tiny station: capacity 3, 1 bike, target 3 -> 2 dock rooms, 2 deficit.
    p = RebalancingProblem(
        stations=(Station("A", "A", 0.0, 0.0, bikes=1, capacity=3, target=3),),
        costs=RebalancingCosts(),
    )
    plan = allocate_supply(p, 10, place_surplus=True)
    assert plan.allocated == 2  # only 2 docks exist
    assert plan.held == 8
    assert plan.shortage_after == 0


def test_negative_extra_rejected() -> None:
    with pytest.raises(ValueError):
        allocate_supply(_problem(), -1)

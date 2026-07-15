"""Optimal extra-bike allocation. CLAUDE.md section 14 + section 17.

The allocator distributes M operator-supplied bikes to minimise the asymmetric operational cost.
Because the objective is separable and convex, the greedy marginal allocation is globally optimal;
these tests pin that (greedy cost == exhaustive optimum) plus the honest-leftover and hard-
constraint behaviour.
"""

from __future__ import annotations

from config.rebalancing import RebalancingCosts
from optimization.classical.allocation import allocate_brute_force, allocate_extra_bikes
from optimization.classical.problem import RebalancingProblem, Station


def _station(sid: str, bikes: int, capacity: int, target: int) -> Station:
    # Coordinates are irrelevant to allocation (no distance term); use JC-area points.
    return Station(sid, sid, 40.72, -74.04, bikes=bikes, capacity=capacity, target=target)


def _problem(*stations: Station) -> RebalancingProblem:
    return RebalancingProblem(stations=tuple(stations), costs=RebalancingCosts())


def test_zero_extra_is_a_no_op() -> None:
    p = _problem(_station("A", 2, 10, 6), _station("B", 5, 10, 5))
    r = allocate_extra_bikes(p, 0)
    assert r.placed == 0 and r.leftover == 0
    assert all(s.added == 0 for s in r.stations)
    assert r.benefit == 0.0


def test_fills_worst_deficit_first() -> None:
    # A needs 4, B needs 1. With 3 bikes, all should go to the larger deficit (A).
    p = _problem(_station("A", 2, 10, 6), _station("B", 4, 10, 5))
    r = allocate_extra_bikes(p, 3)
    by_id = {s.station_id: s for s in r.stations}
    assert by_id["A"].added == 3
    assert by_id["B"].added == 0
    assert r.shortage_units_after == r.shortage_units_before - 3
    assert r.benefit == 3 * p.costs.shortage_cost


def test_leftover_held_back_when_no_beneficial_placement() -> None:
    # Total deficit is 4 (A:3, B:1). Supplying 10 places only 4; the rest is held in the depot,
    # because a bike above target would only add overflow.
    p = _problem(_station("A", 3, 10, 6), _station("B", 4, 10, 5))
    r = allocate_extra_bikes(p, 10)
    assert r.placed == 4
    assert r.leftover == 6
    assert r.shortage_units_after == 0
    assert r.overflow_units_after == r.overflow_units_before  # never pushed above target


def test_respects_dock_capacity() -> None:
    # A is below target but has only 1 dock free; the allocator cannot exceed capacity.
    p = _problem(_station("A", 9, 10, 10), _station("B", 3, 10, 6))
    r = allocate_extra_bikes(p, 5)
    by_id = {s.station_id: s for s in r.stations}
    assert by_id["A"].added <= 1
    assert by_id["A"].bikes_after <= by_id["A"].capacity


def test_never_places_more_than_supplied() -> None:
    p = _problem(_station("A", 0, 10, 8), _station("B", 0, 10, 8))
    r = allocate_extra_bikes(p, 5)
    assert r.placed == 5
    assert sum(s.added for s in r.stations) == 5


def test_greedy_matches_brute_force_optimum() -> None:
    # A separable/convex objective => greedy is optimal. Validate against exhaustive search on a
    # few crafted small instances (mirrors the QUBO brute-force validation pattern, §14.2).
    instances = [
        _problem(_station("A", 2, 8, 6), _station("B", 4, 8, 5), _station("C", 1, 8, 4)),
        _problem(_station("A", 5, 10, 5), _station("B", 0, 6, 6), _station("C", 3, 9, 7)),
        _problem(_station("A", 1, 4, 4), _station("B", 2, 5, 3)),
    ]
    for p in instances:
        for extra in range(0, 8):
            greedy = allocate_extra_bikes(p, extra)
            _, brute_cost = allocate_brute_force(p, extra)
            assert greedy.cost_after == brute_cost, (
                f"greedy {greedy.cost_after} != optimum {brute_cost} at extra={extra}"
            )


def test_benefit_equals_cost_reduction() -> None:
    p = _problem(_station("A", 0, 10, 6), _station("B", 2, 10, 5))
    r = allocate_extra_bikes(p, 4)
    assert r.benefit == round(r.cost_before - r.cost_after, 4)
    assert r.benefit >= 0.0

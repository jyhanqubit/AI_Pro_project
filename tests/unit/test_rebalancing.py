"""Unit tests for classical rebalancing. CLAUDE.md sections 14.1, 17.

Covers: the pure objective, explicit feasibility rejection of bad moves, the greedy baseline
(always feasible, never worse than doing nothing), and MILP optimality checked against the exact
enumeration oracle (and never worse than greedy).
"""

from __future__ import annotations

import pytest

from config.rebalancing import RebalancingCosts
from optimization.classical.enumeration import enumerate_plans
from optimization.classical.feasibility import check_feasibility
from optimization.classical.greedy import greedy_plan
from optimization.classical.milp import milp_plan
from optimization.classical.objective import do_nothing_cost, plan_cost
from optimization.classical.problem import (
    Move,
    RebalancingPlan,
    RebalancingProblem,
    Station,
)


def _problem(vehicle_capacity: int = 18) -> RebalancingProblem:
    # Two surplus stations feed three deficit stations (Jersey City / Hoboken geometry).
    stations = (
        Station(
            "GRV", "Grove St", 40.7196, -74.0431, bikes=16, capacity=20, target=6, zone_id="z4"
        ),
        Station(
            "EXC", "Exchange Pl", 40.7166, -74.0329, bikes=13, capacity=18, target=5, zone_id="z5"
        ),
        Station(
            "HOB",
            "Hoboken Terminal",
            40.7360,
            -74.0301,
            bikes=2,
            capacity=20,
            target=9,
            zone_id="z1",
        ),
        Station(
            "CTH", "City Hall", 40.7377, -74.0324, bikes=3, capacity=18, target=8, zone_id="z2"
        ),
        Station("NEW", "Newport", 40.7272, -74.0337, bikes=4, capacity=16, target=8, zone_id="z3"),
    )
    return RebalancingProblem(
        stations=stations, costs=RebalancingCosts(), vehicle_capacity=vehicle_capacity
    )


def test_station_invariants_rejected() -> None:
    with pytest.raises(ValueError):
        Station("X", "x", 0.0, 0.0, bikes=5, capacity=3, target=1)  # bikes > capacity
    with pytest.raises(ValueError):
        Station("X", "x", 0.0, 0.0, bikes=1, capacity=3, target=9)  # target > capacity


def test_objective_is_asymmetric_and_pure() -> None:
    p = _problem()
    empty = RebalancingPlan(moves=(), solver="none")
    cost = plan_cost(p, empty)
    # Deficits: HOB 7 + CTH 5 + NEW 4 = 16 shortage units; surplus overflow = 10 + 8 = 18.
    assert cost.shortage_units == 16
    assert cost.overflow_units == 18
    # Shortage weighted more heavily than overflow (asymmetric).
    assert cost.shortage_cost == pytest.approx(3.0 * 16)
    assert cost.overflow_cost == pytest.approx(1.0 * 18)


def test_feasibility_rejects_bad_moves() -> None:
    p = _problem()
    # Move more bikes than the origin has.
    bad = RebalancingPlan(moves=(Move("HOB", "CTH", 99, 1.0),), solver="bad")
    report = check_feasibility(p, bad)
    assert not report.feasible
    assert report.reason and "exceeds available bikes" in report.reason

    # Exceed destination capacity.
    over = RebalancingPlan(moves=(Move("GRV", "NEW", 16, 1.0),), solver="bad")
    assert not check_feasibility(p, over).feasible  # NEW cap 16, would reach 20

    # Non-positive / non-integer quantity.
    assert not check_feasibility(p, RebalancingPlan((Move("GRV", "HOB", 0, 1.0),), "bad")).feasible

    # Exceed the vehicle capacity limit.
    huge = RebalancingPlan(
        moves=(Move("GRV", "HOB", 10, 1.0), Move("EXC", "CTH", 10, 1.0)), solver="bad"
    )
    assert not check_feasibility(_problem(vehicle_capacity=15), huge).feasible


def test_feasibility_reports_unknown_station_without_crashing() -> None:
    # A move referencing a station absent from the problem must be reported as infeasible,
    # not raise (the defensive contract, §14.1 "report infeasibility explicitly").
    p = _problem()
    plan = RebalancingPlan(moves=(Move("ZZZ", "HOB", 1, 1.0),), solver="bad")
    report = check_feasibility(p, plan)  # must not raise KeyError
    assert not report.feasible
    assert report.reason and "unknown station" in report.reason


def test_greedy_is_always_feasible_and_not_worse_than_nothing() -> None:
    p = _problem()
    plan = greedy_plan(p)
    assert check_feasibility(p, plan).feasible
    assert plan_cost(p, plan).total_cost <= do_nothing_cost(p).total_cost


def test_milp_matches_enumeration_and_beats_or_ties_greedy() -> None:
    p = _problem()
    mplan, mcost = milp_plan(p)
    eplan, ecost = enumerate_plans(p)
    gcost = plan_cost(p, greedy_plan(p))

    assert check_feasibility(p, mplan).feasible
    assert mcost.total_cost == pytest.approx(ecost.total_cost)  # MILP is optimal
    assert mcost.total_cost <= gcost.total_cost + 1e-9  # never worse than greedy


def test_milp_respects_binding_vehicle_capacity() -> None:
    # Total deficit is 16 but only 6 bikes may move: shortage cannot be fully eliminated.
    p = _problem(vehicle_capacity=6)
    plan, cost = milp_plan(p)
    assert check_feasibility(p, plan).feasible
    assert plan.total_moved <= 6
    assert cost.shortage_units >= 16 - 6

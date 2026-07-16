"""Exact rebalancing solver by enumeration. CLAUDE.md section 14.1.

Brute-forces the optimum over small instances and serves as the independent correctness oracle
for the MILP and QUBO solvers (sections 14.1, 14.2). It is exact but exponential, so it guards
its own search-space size and raises rather than hang.

Search-space reduction (objective-preserving): for this asymmetric objective with positive
costs, an optimal plan never drains an origin below its target nor pushes a destination above
its target (both would only add cost). So candidate moves are restricted to
``surplus-origin -> deficit-destination`` edges with per-edge quantity in
``[0, min(origin_surplus, destination_deficit)]``. Full feasibility (aggregate outflow and the
vehicle-capacity limit) is then enforced by ``check_feasibility``.
"""

from __future__ import annotations

from itertools import product

from .feasibility import check_feasibility
from .objective import CostBreakdown, plan_cost
from .problem import Move, RebalancingPlan, RebalancingProblem

# Hard cap on the number of quantity combinations enumerated, to keep the oracle honest about
# only being usable on small instances.
MAX_COMBINATIONS = 5_000_000


class ExactSolverError(RuntimeError):
    """Raised when the enumeration search space is too large to brute-force."""


def _candidate_edges(problem: RebalancingProblem) -> list[tuple[int, int, int]]:
    """(origin_idx, dest_idx, max_qty) for surplus->deficit edges."""
    edges: list[tuple[int, int, int]] = []
    for i, origin in enumerate(problem.stations):
        if origin.surplus <= 0:
            continue
        for j, dest in enumerate(problem.stations):
            if i == j or dest.deficit <= 0:
                continue
            cap = min(origin.surplus, dest.deficit, problem.vehicle_capacity)
            if cap > 0:
                edges.append((i, j, cap))
    return edges


def _combination_count(edges: list[tuple[int, int, int]], ceiling: int) -> int:
    """Enumeration-space size (product of per-edge (cap+1)); short-circuits past ``ceiling``."""
    combos = 1
    for _, _, cap in edges:
        combos *= cap + 1
        if combos > ceiling:
            break
    return combos


def bounded_subproblem(
    problem: RebalancingProblem,
    *,
    max_origins: int = 2,
    max_dests: int = 2,
    max_combinations: int = 500_000,
) -> RebalancingProblem:
    """Carve a small, exactly-enumerable slice out of a large problem (§14.1).

    Full-scale rebalancing is intractable for the exact solver (that is why the MILP exists), so
    the exact oracle is run on a realistic-but-tractable slice: the largest-surplus origins and
    largest-deficit destinations, with the vehicle capacity lowered until the enumeration space is
    under ``max_combinations``. Both the MILP and the exact solver run on this identical slice, so
    any agreement/disagreement is a genuine cross-check. Deterministic (ties broken by station_id).
    """
    origins = sorted(
        (s for s in problem.stations if s.surplus > 0),
        key=lambda s: (-s.surplus, s.station_id),
    )[:max_origins]
    dests = sorted(
        (s for s in problem.stations if s.deficit > 0),
        key=lambda s: (-s.deficit, s.station_id),
    )[:max_dests]
    picked = {s.station_id for s in (*origins, *dests)}
    stations = tuple(s for s in problem.stations if s.station_id in picked)

    vcap = problem.vehicle_capacity
    while vcap > 1:
        candidate = RebalancingProblem(
            stations=stations, costs=problem.costs, vehicle_capacity=vcap
        )
        if _combination_count(_candidate_edges(candidate), max_combinations) <= max_combinations:
            return candidate
        vcap -= 1
    return RebalancingProblem(stations=stations, costs=problem.costs, vehicle_capacity=max(vcap, 0))


def enumerate_plans(problem: RebalancingProblem) -> tuple[RebalancingPlan, CostBreakdown]:
    """Return the cost-minimising feasible plan and its cost breakdown."""
    edges = _candidate_edges(problem)

    combos = _combination_count(edges, MAX_COMBINATIONS)
    if combos > MAX_COMBINATIONS:
        raise ExactSolverError(
            f"enumeration space {combos}+ exceeds cap {MAX_COMBINATIONS}; use MILP instead"
        )

    best_plan = RebalancingPlan(moves=(), solver="exact")
    best_cost = plan_cost(problem, best_plan)

    for quantities in product(*[range(cap + 1) for _, _, cap in edges]):
        moves = tuple(
            Move(
                origin_id=problem.stations[i].station_id,
                destination_id=problem.stations[j].station_id,
                quantity=q,
                distance_km=round(problem.distance_km(i, j), 4),
            )
            for (i, j, _), q in zip(edges, quantities, strict=True)
            if q > 0
        )
        plan = RebalancingPlan(moves=moves, solver="exact")
        if not check_feasibility(problem, plan).feasible:
            continue
        cost = plan_cost(problem, plan)
        if cost.total_cost < best_cost.total_cost:
            best_cost = cost
            best_plan = plan

    return best_plan, best_cost

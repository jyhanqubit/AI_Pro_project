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


def enumerate_plans(problem: RebalancingProblem) -> tuple[RebalancingPlan, CostBreakdown]:
    """Return the cost-minimising feasible plan and its cost breakdown."""
    edges = _candidate_edges(problem)

    combos = 1
    for _, _, cap in edges:
        combos *= cap + 1
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

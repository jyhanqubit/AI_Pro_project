"""Greedy feasible rebalancing baseline. CLAUDE.md section 14.1 (build order step 1).

Repeatedly moves bikes from the surplus station to the deficit station with the highest
marginal cost reduction, until no beneficial move remains or the vehicle is full. The result is
always feasible and never worse than doing nothing: a bike is moved only while the gain
(shortage relieved + overflow relieved - relocation distance cost) is strictly positive. It is
not guaranteed optimal — that is the MILP's job — so it serves as the honest lower bar.
"""

from __future__ import annotations

from .problem import Move, RebalancingPlan, RebalancingProblem


def greedy_plan(problem: RebalancingProblem) -> RebalancingPlan:
    n = len(problem.stations)
    bikes = [s.bikes for s in problem.stations]
    target = [s.target for s in problem.stations]
    c = problem.costs
    remaining_vehicle = problem.vehicle_capacity

    # Accumulate moves per directed pair so the plan lists one Move per (origin, dest).
    moved: dict[tuple[int, int], int] = {}

    while remaining_vehicle > 0:
        best_gain = 0.0
        best: tuple[int, int] | None = None
        for i in range(n):
            if bikes[i] <= target[i]:  # no surplus to give
                continue
            for j in range(n):
                if i == j or bikes[j] >= target[j]:  # no deficit to fill
                    continue
                dist = problem.distance_km(i, j)
                gain = c.shortage_cost + c.overflow_cost - c.distance_cost * dist
                if gain > best_gain:
                    best_gain = gain
                    best = (i, j)
        if best is None:
            break
        i, j = best
        qty = min(bikes[i] - target[i], target[j] - bikes[j], remaining_vehicle)
        if qty <= 0:
            break
        bikes[i] -= qty
        bikes[j] += qty
        remaining_vehicle -= qty
        moved[(i, j)] = moved.get((i, j), 0) + qty

    moves = tuple(
        Move(
            origin_id=problem.stations[i].station_id,
            destination_id=problem.stations[j].station_id,
            quantity=q,
            distance_km=round(problem.distance_km(i, j), 4),
        )
        for (i, j), q in moved.items()
    )
    return RebalancingPlan(moves=moves, solver="greedy")

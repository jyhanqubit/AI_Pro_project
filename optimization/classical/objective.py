"""Operational objective for a rebalancing plan. CLAUDE.md section 14.1.

Pure cost function over a plan (no solving here). The objective is the asymmetric operational
cost:

    cost = shortage_cost * sum_i max(0, target_i - final_i)      # unmet demand
         + overflow_cost * sum_i max(0, final_i - target_i)      # wasted / dock-blocking
         + distance_cost * sum_moves distance_km * quantity      # relocation effort

``final_i`` is the post-plan inventory at station ``i``. The function is total: it scores any
plan, feasible or not (feasibility is enforced elsewhere), which lets solvers and tests compare
plans on one consistent scale.
"""

from __future__ import annotations

from dataclasses import dataclass

from .problem import RebalancingPlan, RebalancingProblem


@dataclass(frozen=True)
class CostBreakdown:
    shortage_units: int
    overflow_units: int
    distance_km: float
    shortage_cost: float
    overflow_cost: float
    distance_cost: float
    total_cost: float


def imbalance_units(problem: RebalancingProblem, final: dict[str, int]) -> tuple[int, int]:
    """Total (shortage_units, overflow_units) across all stations for a final inventory."""
    shortage = 0
    overflow = 0
    for s in problem.stations:
        f = final[s.station_id]
        shortage += max(0, s.target - f)
        overflow += max(0, f - s.target)
    return shortage, overflow


def plan_cost(problem: RebalancingProblem, plan: RebalancingPlan) -> CostBreakdown:
    """Score a plan with the asymmetric operational objective (section 14.1)."""
    final = plan.final_inventory(problem)
    shortage_units, overflow_units = imbalance_units(problem, final)
    distance_km = sum(m.distance_km * m.quantity for m in plan.moves)

    c = problem.costs
    shortage_cost = c.shortage_cost * shortage_units
    overflow_cost = c.overflow_cost * overflow_units
    distance_cost = c.distance_cost * distance_km
    return CostBreakdown(
        shortage_units=shortage_units,
        overflow_units=overflow_units,
        distance_km=round(distance_km, 4),
        shortage_cost=round(shortage_cost, 4),
        overflow_cost=round(overflow_cost, 4),
        distance_cost=round(distance_cost, 4),
        total_cost=round(shortage_cost + overflow_cost + distance_cost, 4),
    )


def do_nothing_cost(problem: RebalancingProblem) -> CostBreakdown:
    """Cost of the empty plan (the baseline every solver must not do worse than)."""
    return plan_cost(problem, RebalancingPlan(moves=(), solver="do_nothing"))

"""Build & solve the demo rebalancing problem for the API. CLAUDE.md sections 12, 13, 14.

Turns the offline replay state into an operator-facing relocation plan (the "Act" step of
Alert -> Why -> Simulate -> Act). Station inventory comes from the curated rebalancing fixture;
each station's *target* is its normal-hour base target raised by the event-aware forecast delta
in its H3 zone as-of the cutoff — a transparent, clearly-labelled demo heuristic
(``demo-heuristic-v1``, Historical Replay), never the measured Phase 06 model (section 22).

The plan is produced by the classical solvers (greedy or MILP) and always passes an explicit
feasibility check before it is returned. Quantum Research Mode (QUBO/QAOA) is never used here
(section 3).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from config.collectors import REBALANCING_DEMO_FIXTURE
from optimization.classical.allocation import SupplyAllocationPlan, allocate_supply
from optimization.classical.feasibility import check_feasibility
from optimization.classical.greedy import greedy_plan
from optimization.classical.milp import milp_plan
from optimization.classical.objective import CostBreakdown, do_nothing_cost, plan_cost
from optimization.classical.problem import RebalancingPlan, RebalancingProblem, Station
from pipelines.features.zones import zone_for

from .replay import ReplayEngine


@dataclass(frozen=True)
class StationState:
    station_id: str
    name: str
    zone_id: str
    bikes_before: int
    bikes_after: int
    target: int
    capacity: int
    base_target: int
    shortage_before: int
    shortage_after: int


@dataclass(frozen=True)
class RebalancingSolution:
    method: str
    feasible: bool
    infeasibility_reason: str | None
    plan: RebalancingPlan
    cost: CostBreakdown
    baseline_cost: CostBreakdown
    shortage_reduction: int
    overflow_reduction: int
    stations: tuple[StationState, ...]
    vehicle_capacity: int


def _load_fixture() -> dict:
    return json.loads(REBALANCING_DEMO_FIXTURE.read_text(encoding="utf-8"))


def build_problem(
    engine: ReplayEngine, cutoff: datetime, *, vehicle_capacity: int | None = None
) -> tuple[RebalancingProblem, dict[str, int]]:
    """Build the as-of rebalancing problem; also return each station's base_target."""
    fixture = _load_fixture()
    # Event-aware forecast delta per demo zone as-of the cutoff (labelled demo heuristic).
    zone_delta = {zf.zone_id: zf.forecast_delta for zf in engine.forecasts(cutoff)}

    stations: list[Station] = []
    base_targets: dict[str, int] = {}
    for s in fixture["stations"]:
        zone = zone_for(float(s["lat"]), float(s["lng"]))
        base_target = int(s["base_target"])
        # Raise the target by predicted extra departures in this zone (>= 0), clamp to capacity.
        surge = max(0, round(zone_delta.get(zone, 0.0)))
        capacity = int(s["capacity"])
        target = min(capacity, base_target + surge)
        stations.append(
            Station(
                station_id=str(s["station_id"]),
                name=str(s["name"]),
                lat=float(s["lat"]),
                lng=float(s["lng"]),
                bikes=int(s["bikes_available"]),
                capacity=capacity,
                target=target,
                zone_id=zone,
            )
        )
        base_targets[str(s["station_id"])] = base_target

    vcap = vehicle_capacity if vehicle_capacity is not None else int(fixture["vehicle_capacity"])
    problem = RebalancingProblem(stations=tuple(stations), vehicle_capacity=vcap)
    return problem, base_targets


def solve(
    engine: ReplayEngine,
    cutoff: datetime,
    *,
    method: str = "milp",
    vehicle_capacity: int | None = None,
) -> RebalancingSolution:
    problem, base_targets = build_problem(engine, cutoff, vehicle_capacity=vehicle_capacity)

    if method == "greedy":
        plan = greedy_plan(problem)
        cost = plan_cost(problem, plan)
    else:
        method = "milp"
        plan, cost = milp_plan(problem)

    report = check_feasibility(problem, plan)
    baseline = do_nothing_cost(problem)
    final = plan.final_inventory(problem)

    states = tuple(
        StationState(
            station_id=s.station_id,
            name=s.name,
            zone_id=s.zone_id or "",
            bikes_before=s.bikes,
            bikes_after=final[s.station_id],
            target=s.target,
            capacity=s.capacity,
            base_target=base_targets[s.station_id],
            shortage_before=max(0, s.target - s.bikes),
            shortage_after=max(0, s.target - final[s.station_id]),
        )
        for s in problem.stations
    )

    return RebalancingSolution(
        method=method,
        feasible=report.feasible,
        infeasibility_reason=report.reason,
        plan=plan,
        cost=cost,
        baseline_cost=baseline,
        shortage_reduction=baseline.shortage_units - cost.shortage_units,
        overflow_reduction=baseline.overflow_units - cost.overflow_units,
        stations=states,
        vehicle_capacity=problem.vehicle_capacity,
    )


@dataclass(frozen=True)
class AllocationStationState:
    station_id: str
    name: str
    zone_id: str
    bikes_before: int
    bikes_after: int
    added: int
    target: int
    base_target: int
    capacity: int
    deficit_before: int
    deficit_after: int


@dataclass(frozen=True)
class SupplyAllocationSolution:
    """Result of allocating ``extra_bikes`` new units across the demo stations."""

    plan: SupplyAllocationPlan
    current_total_bikes: int
    stations: tuple[AllocationStationState, ...]


def allocate(
    engine: ReplayEngine,
    cutoff: datetime,
    extra_bikes: int,
    *,
    place_surplus: bool = False,
) -> SupplyAllocationSolution:
    """Allocate ``extra_bikes`` new bikes into the as-of demo problem for the largest benefit.

    Unlike :func:`solve` (which relocates existing bikes between stations), this injects new supply:
    the operator has ``current_total_bikes`` deployed now and wants to add ``extra_bikes`` more. The
    plan fills event-aware deficits first (see :mod:`optimization.classical.allocation`).
    """
    problem, base_targets = build_problem(engine, cutoff)
    plan = allocate_supply(problem, extra_bikes, place_surplus=place_surplus)

    added_by_id = {a.station_id: a.added for a in plan.allocations}
    current_total = sum(s.bikes for s in problem.stations)

    states = tuple(
        AllocationStationState(
            station_id=s.station_id,
            name=s.name,
            zone_id=s.zone_id or "",
            bikes_before=s.bikes,
            bikes_after=s.bikes + added_by_id.get(s.station_id, 0),
            added=added_by_id.get(s.station_id, 0),
            target=s.target,
            base_target=base_targets[s.station_id],
            capacity=s.capacity,
            deficit_before=s.deficit,
            deficit_after=max(0, s.target - (s.bikes + added_by_id.get(s.station_id, 0))),
        )
        for s in problem.stations
    )

    return SupplyAllocationSolution(
        plan=plan,
        current_total_bikes=current_total,
        stations=states,
    )

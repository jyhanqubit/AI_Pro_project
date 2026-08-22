"""V2-04 — Multi-period rebalancing under four policies (No Action / Greedy / MILP / MPC).

A receding-horizon simulator over a small H3-zone network. Each hour a policy sets a per-zone
target inventory from the demand *forecast*, rebalances toward it with a per-period solver
(reusing the tested greedy / MILP solvers), then the *realized* net flow hits and any unmet
departures (shortage) or dock overflows are charged on the V2-02 ledger. Inventory rolls forward.

Policies differ only in how they set the target and how well they solve the per-period move:

    No Action  : never moves (target = current inventory)
    Greedy     : 1-hour-ahead forecast target, greedy (feasible, suboptimal) moves
    MILP       : 1-hour-ahead forecast target, exact single-period optimum
    MPC        : H-hour-ahead forecast target (receding horizon), exact moves
    Oracle     : H-hour-ahead target from the REALIZED flow (perfect foresight) — upper bound

MPC uses only the forecast, never future truth (no leakage); Oracle is the offline ceiling, so
regret = Oracle net − policy net ≥ 0. The demand is a documented, seeded commute scenario, so the
dollar outputs are `simulated` (a policy comparison), not a measured business result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from config.rebalancing import RebalancingCosts
from contracts.v2.ledger import LedgerAssumptions
from optimization.classical.greedy import greedy_plan
from optimization.classical.milp import milp_plan
from optimization.classical.problem import RebalancingPlan, RebalancingProblem, Station


@dataclass(frozen=True)
class ZoneSpec:
    zone_id: str
    lat: float
    lng: float
    capacity: int
    kind: str  # "residential" (morning net-out) or "commercial" (morning net-in)
    amplitude: float


def default_network(n_zones: int = 8) -> list[ZoneSpec]:
    """A small line-network of alternating residential/commercial H3-like zones (~1km apart)."""
    zones: list[ZoneSpec] = []
    for i in range(n_zones):
        kind = "residential" if i % 2 == 0 else "commercial"
        zones.append(
            ZoneSpec(
                zone_id=f"Z{i:02d}",
                lat=40.70 + 0.009 * i,  # ~1km latitude spacing
                lng=-74.01,
                capacity=40,
                kind=kind,
                amplitude=12.0 + 2.0 * (i % 3),
            )
        )
    return zones


def _commute_shape(hour_of_day: int, kind: str) -> float:
    """Net flow (arrivals − departures) shape in [-1, 1]. Residential: AM out, PM in."""
    # Morning peak ~8h, evening peak ~18h.
    am = math.exp(-((hour_of_day - 8) ** 2) / 8.0)
    pm = math.exp(-((hour_of_day - 18) ** 2) / 8.0)
    if kind == "residential":
        return -am + pm  # bikes leave in the morning, return in the evening
    return am - pm  # commercial: opposite


def demand_series(zones: list[ZoneSpec], hours: int, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """Return (forecast_net, realized_net) arrays of shape (hours, n_zones).

    Forecast is the deterministic commute mean; realized adds seeded Gaussian noise (the demand
    uncertainty the policies must cope with). Documented scenario — labeled `simulated`.
    """
    rng = np.random.default_rng(seed)
    z = len(zones)
    fc = np.zeros((hours, z))
    for t in range(hours):
        hod = t % 24
        for j, zs in enumerate(zones):
            fc[t, j] = zs.amplitude * _commute_shape(hod, zs.kind)
    noise = rng.normal(0.0, 3.0, size=(hours, z))
    realized = fc + noise
    return fc, realized


def _target_from_forecast(bikes: np.ndarray, fc_window: np.ndarray, capacity: np.ndarray) -> list[int]:
    """Target inventory to enter the window: cover expected outflow, leave room for inflow.

    ``fc_window`` is (h, n) forecast net flow over the look-ahead. Cumulative net outflow raises
    the target (hold bikes), cumulative net inflow lowers it (leave dock room)."""
    cum = fc_window.sum(axis=0)  # net over the window per zone (+ inflow, − outflow)
    # Want ~ capacity/2 as neutral, shifted by the expected net: net outflow (cum<0) -> hold more.
    target = np.clip(np.rint(capacity / 2.0 - cum), 0, capacity)
    return [int(x) for x in target]


def _solve_period(bikes, capacity, target, zones, costs, vehicle_capacity, solver):
    stations = tuple(
        Station(z.zone_id, z.zone_id, z.lat, z.lng, int(bikes[j]), int(capacity[j]), int(target[j]))
        for j, z in enumerate(zones)
    )
    problem = RebalancingProblem(stations=stations, costs=costs, vehicle_capacity=vehicle_capacity)
    if solver == "greedy":
        plan = greedy_plan(problem)
    else:
        plan, _ = milp_plan(problem)
    return problem, plan


@dataclass
class PolicyResult:
    policy: str
    shortage_units: float
    overflow_units: float
    moved_units: float
    shortage_cost: float
    overflow_cost: float
    relocation_cost: float
    total_cost: float
    net: float
    feasible: bool
    infeasible_periods: int


def simulate(policy: str, zones: list[ZoneSpec], fc: np.ndarray, realized: np.ndarray,
             A: LedgerAssumptions, *, horizon: int = 6, vehicle_capacity: int = 18,
             margin_baseline: float = 0.0) -> PolicyResult:
    """Run one policy over the whole series and tally the ledger. ``net`` = −total_cost (+const)."""
    hours, z = realized.shape
    capacity = np.array([zs.capacity for zs in zones], dtype=float)
    bikes = capacity / 2.0
    # Map the ledger onto the per-period solver's cost weights (unit distances ~1km apart).
    costs = RebalancingCosts(
        shortage_cost=A.shortage_externality,
        overflow_cost=A.overflow_penalty,
        distance_cost=A.reposition_cost_per_unit,
    )
    tot_short = tot_over = tot_moved = 0.0
    infeasible = 0

    for t in range(hours):
        # 1) decide + rebalance (uses FORECAST for all policies except oracle) ----------------
        if policy == "no_action":
            pass
        else:
            if policy == "oracle":
                window = realized[t:t + horizon]  # perfect foresight (upper bound)
                h_solver = "milp"
            elif policy == "mpc":
                window = fc[t:t + horizon]
                h_solver = "milp"
            elif policy == "milp":
                window = fc[t:t + 1]
                h_solver = "milp"
            elif policy == "greedy":
                window = fc[t:t + 1]
                h_solver = "greedy"
            else:
                raise ValueError(f"unknown policy {policy}")
            target = _target_from_forecast(bikes, window, capacity)
            problem, plan = _solve_period(bikes, capacity, target, zones, costs, vehicle_capacity, h_solver)
            from optimization.classical.feasibility import check_feasibility

            if not check_feasibility(problem, plan).feasible:
                infeasible += 1
                plan = RebalancingPlan(moves=(), solver=h_solver)  # reject infeasible -> no move
            for m in plan.moves:
                i = problem.index_of(m.origin_id)
                j = problem.index_of(m.destination_id)
                bikes[i] -= m.quantity
                bikes[j] += m.quantity
                tot_moved += m.quantity

        # 2) realized demand hits: net flow, with shortage (unmet out) / overflow (no dock) -----
        for j in range(z):
            net = realized[t, j]
            if net < 0:  # net departures
                demand_out = -net
                served = min(bikes[j], demand_out)
                tot_short += demand_out - served  # unmet departures
                bikes[j] -= served
            else:  # net arrivals
                room = capacity[j] - bikes[j]
                accepted = min(room, net)
                tot_over += net - accepted  # bikes with no dock (overflow)
                bikes[j] += accepted

    shortage_cost = tot_short * A.shortage_externality
    overflow_cost = tot_over * A.overflow_penalty
    relocation_cost = tot_moved * A.reposition_cost_per_unit
    total_cost = shortage_cost + overflow_cost + relocation_cost
    net = margin_baseline - total_cost
    return PolicyResult(
        policy=policy, shortage_units=tot_short, overflow_units=tot_over, moved_units=tot_moved,
        shortage_cost=shortage_cost, overflow_cost=overflow_cost, relocation_cost=relocation_cost,
        total_cost=total_cost, net=net, feasible=infeasible == 0, infeasible_periods=infeasible,
    )

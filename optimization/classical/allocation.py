"""Optimal allocation of *extra* bikes into the network. CLAUDE.md section 14.

The existing solvers (``greedy``, ``milp``) *relocate* bikes between stations (total conserved).
This module answers a different operator question:

    "The system has N bikes right now. I want to inject M more bikes.
     How should I distribute them to maximise operational benefit?"

The operator supplies ``M``; the allocator distributes those bikes across stations to minimise the
same asymmetric operational cost the relocation solvers use (shortage weighted above overflow,
``config/rebalancing.py``), subject to hard constraints:

* ``added_i >= 0`` integer,
* ``bikes_i + added_i <= capacity_i`` (never exceed a station's docks),
* ``sum_i added_i <= M`` (never place more than supplied).

Because each station's cost is **separable and convex** in the bikes added (each unit below target
removes one shortage unit worth ``shortage_cost``; each unit above target adds one overflow unit
worth ``overflow_cost``), a greedy that repeatedly places the next bike where its *marginal benefit*
is largest is globally optimal. We only place a bike while its marginal benefit is strictly
positive, so surplus bikes beyond what the network can usefully absorb are honestly reported as
held back (placing them would only create overflow) rather than dumped to inflate a number.

``allocate_brute_force`` is an independent optimum used only in tests to validate the greedy.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from .objective import imbalance_units
from .problem import RebalancingProblem


@dataclass(frozen=True)
class StationAllocation:
    station_id: str
    name: str
    zone_id: str
    bikes_before: int
    added: int
    bikes_after: int
    target: int
    capacity: int
    shortage_before: int
    shortage_after: int


@dataclass(frozen=True)
class AllocationResult:
    extra_requested: int
    placed: int
    leftover: int
    shortage_units_before: int
    shortage_units_after: int
    overflow_units_before: int
    overflow_units_after: int
    cost_before: float
    cost_after: float
    benefit: float  # cost_before - cost_after (>= 0)
    stations: tuple[StationAllocation, ...]


def _cost(problem: RebalancingProblem, inventory: dict[str, int]) -> float:
    shortage, overflow = imbalance_units(problem, inventory)
    c = problem.costs
    return c.shortage_cost * shortage + c.overflow_cost * overflow


def allocate_extra_bikes(problem: RebalancingProblem, extra: int) -> AllocationResult:
    """Greedy marginal-benefit allocation of ``extra`` bikes (globally optimal, see module doc)."""
    if extra < 0:
        raise ValueError("extra must be >= 0")

    added: dict[str, int] = {s.station_id: 0 for s in problem.stations}

    for _ in range(extra):
        # Beneficial candidates = stations still below target with dock room. Each such unit
        # removes one shortage unit (marginal benefit = shortage_cost); a bike placed above
        # target would only add overflow, so it is never beneficial and is skipped.
        candidates = [
            s
            for s in problem.stations
            if (s.bikes + added[s.station_id]) < s.target
            and (s.bikes + added[s.station_id]) < s.capacity
        ]
        if not candidates:
            break  # nothing left worth placing; hold remaining bikes in the depot
        # Tie-break: worst remaining deficit first, then station id (deterministic).
        best = min(
            candidates,
            key=lambda s: (-(s.target - (s.bikes + added[s.station_id])), s.station_id),
        )
        added[best.station_id] += 1

    before = {s.station_id: s.bikes for s in problem.stations}
    after = {s.station_id: s.bikes + added[s.station_id] for s in problem.stations}
    short_b, over_b = imbalance_units(problem, before)
    short_a, over_a = imbalance_units(problem, after)
    cost_b = _cost(problem, before)
    cost_a = _cost(problem, after)
    placed = sum(added.values())

    stations = tuple(
        StationAllocation(
            station_id=s.station_id,
            name=s.name,
            zone_id=s.zone_id or "",
            bikes_before=s.bikes,
            added=added[s.station_id],
            bikes_after=s.bikes + added[s.station_id],
            target=s.target,
            capacity=s.capacity,
            shortage_before=max(0, s.target - s.bikes),
            shortage_after=max(0, s.target - (s.bikes + added[s.station_id])),
        )
        for s in problem.stations
    )

    return AllocationResult(
        extra_requested=extra,
        placed=placed,
        leftover=extra - placed,
        shortage_units_before=short_b,
        shortage_units_after=short_a,
        overflow_units_before=over_b,
        overflow_units_after=over_a,
        cost_before=round(cost_b, 4),
        cost_after=round(cost_a, 4),
        benefit=round(cost_b - cost_a, 4),
        stations=stations,
    )


def allocate_brute_force(problem: RebalancingProblem, extra: int) -> tuple[dict[str, int], float]:
    """Exhaustive optimum (test oracle only). Enumerates every feasible allocation.

    Intended for small instances; the search space is ``prod_i (room_i + 1)`` filtered to
    ``sum <= extra``. Returns the best (allocation, cost).
    """
    rooms = [min(extra, s.capacity - s.bikes) for s in problem.stations]
    ids = [s.station_id for s in problem.stations]
    best_alloc: dict[str, int] = {i: 0 for i in ids}
    best_cost = _cost(problem, {s.station_id: s.bikes for s in problem.stations})
    for combo in product(*(range(r + 1) for r in rooms)):
        if sum(combo) > extra:
            continue
        inv = {s.station_id: s.bikes + combo[k] for k, s in enumerate(problem.stations)}
        cost = _cost(problem, inv)
        if cost < best_cost - 1e-9:
            best_cost = cost
            best_alloc = {ids[k]: combo[k] for k in range(len(ids))}
    return best_alloc, round(best_cost, 4)

"""Optimal allocation of NEW bikes into the system. CLAUDE.md section 14.

Distinct from *relocation* (``greedy``/``milp`` move existing bikes between stations): here the
operator injects ``extra_bikes`` brand-new units — "there are ``n`` bikes now, I want to add ``m``
more" — and asks where to place them for the largest operational benefit. There is no relocation
distance and no vehicle tour; the only physical constraint is per-station dock room (a station
cannot exceed its capacity). Benefit is measured as the reduction in the asymmetric operational
cost, where a shortage is weighted above an overflow (section 14.1).

Why greedy is optimal here. The marginal value of the k-th bike placed at station ``i`` is:

    + shortage_cost   while  bikes_i < target_i          (removes one unit of unmet demand)
    - overflow_cost   while  target_i <= bikes_i < cap_i (adds one unit of idle surplus)
      infeasible      once   bikes_i == cap_i            (no dock left)

Every deficit-filling bike is worth exactly ``shortage_cost`` (> 0) and every surplus bike is
worth exactly ``-overflow_cost`` (< 0), independent of which station receives it. The objective is
therefore separable with non-increasing marginal value, so the benefit-maximising allocation is:
fill deficits first (in any order), and only then — if the operator chooses to place the rest —
spill the remainder into whatever dock room is left. This greedy is provably optimal; a unit test
checks it against brute-force enumeration on small instances.

By default only the beneficial (deficit-filling) bikes are placed and the remainder is reported as
``held`` (kept in reserve) — that is the genuinely benefit-maximising plan. Set ``place_surplus``
to also spill the leftover into free docks when the operator insists on deploying all ``m`` now;
those bikes carry a clearly-reported negative marginal benefit.
"""

from __future__ import annotations

from dataclasses import dataclass

from .objective import imbalance_units
from .problem import RebalancingProblem


@dataclass(frozen=True)
class Allocation:
    """Bikes newly placed at one station (``added >= 0``)."""

    station_id: str
    added: int


@dataclass(frozen=True)
class SupplyAllocationPlan:
    """Where ``extra_bikes`` new units go, and the benefit of doing so.

    ``allocated = to_deficit + surplus_placed`` is what physically gets deployed; ``held`` is the
    remainder kept in reserve (either because placing it would only add surplus, or because no dock
    room is left). ``benefit`` is ``baseline_cost - post_cost`` under the section 14.1 objective —
    positive means the allocation reduces operational cost.
    """

    allocations: tuple[Allocation, ...]
    extra_bikes: int  # m requested by the operator
    to_deficit: int  # beneficial bikes: each removes one shortage unit
    surplus_placed: int  # bikes placed above target (each adds one overflow unit)
    held: int  # extra_bikes - to_deficit - surplus_placed (reserve / undeployable)
    shortage_before: int
    shortage_after: int
    overflow_before: int
    overflow_after: int
    benefit: float
    solver: str

    @property
    def allocated(self) -> int:
        return self.to_deficit + self.surplus_placed

    @property
    def shortage_reduction(self) -> int:
        return self.shortage_before - self.shortage_after


def _final_inventory(problem: RebalancingProblem, added: dict[str, int]) -> dict[str, int]:
    return {s.station_id: s.bikes + added.get(s.station_id, 0) for s in problem.stations}


def allocate_supply(
    problem: RebalancingProblem,
    extra_bikes: int,
    *,
    place_surplus: bool = False,
) -> SupplyAllocationPlan:
    """Allocate ``extra_bikes`` new units to maximise operational benefit (section 14).

    Deterministic: deficits are filled largest-first with the station id as a tiebreak, so the same
    problem and ``extra_bikes`` always yield the same plan.
    """
    if extra_bikes < 0:
        raise ValueError(f"extra_bikes must be >= 0, got {extra_bikes}")

    stations = problem.stations
    added: dict[str, int] = {s.station_id: 0 for s in stations}
    remaining = extra_bikes

    # 1) Fill deficits — every such bike is worth +shortage_cost. Order among deficit stations does
    #    not change total benefit (all equal), so pick the largest deficit first for a sensible,
    #    deterministic plan; deficit <= dock_room always holds (target <= capacity), so this is
    #    feasible without a capacity check here.
    for s in sorted(stations, key=lambda st: (-st.deficit, st.station_id)):
        if remaining <= 0:
            break
        take = min(s.deficit, remaining)
        if take > 0:
            added[s.station_id] += take
            remaining -= take
    to_deficit = extra_bikes - remaining

    # 2) Optionally spill the remainder into free docks — every such bike is worth -overflow_cost,
    #    equal across stations, so distribute deterministically by most free dock room first. Any
    #    bike that cannot be placed (no docks anywhere) stays held.
    surplus_placed = 0
    if place_surplus and remaining > 0:
        free = {s.station_id: s.dock_room - added[s.station_id] for s in stations}
        for s in sorted(stations, key=lambda st: (-free[st.station_id], st.station_id)):
            if remaining <= 0:
                break
            room = free[s.station_id]
            take = min(room, remaining)
            if take > 0:
                added[s.station_id] += take
                remaining -= take
                surplus_placed += take

    held = remaining

    before = imbalance_units(problem, {s.station_id: s.bikes for s in stations})
    after = imbalance_units(problem, _final_inventory(problem, added))
    c = problem.costs
    baseline_cost = c.shortage_cost * before[0] + c.overflow_cost * before[1]
    post_cost = c.shortage_cost * after[0] + c.overflow_cost * after[1]

    allocations = tuple(
        Allocation(station_id=s.station_id, added=added[s.station_id])
        for s in stations
        if added[s.station_id] > 0
    )
    return SupplyAllocationPlan(
        allocations=allocations,
        extra_bikes=extra_bikes,
        to_deficit=to_deficit,
        surplus_placed=surplus_placed,
        held=held,
        shortage_before=before[0],
        shortage_after=after[0],
        overflow_before=before[1],
        overflow_after=after[1],
        benefit=round(baseline_cost - post_cost, 4),
        solver="greedy-allocation",
    )

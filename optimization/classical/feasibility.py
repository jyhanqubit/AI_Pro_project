"""Explicit feasibility checks for a rebalancing plan. CLAUDE.md section 14.1.

A plan is presented to an operator only after this passes (sections 13, 14.1). Infeasibility is
reported explicitly with human-readable reasons — never silently repaired or hidden.

Checked constraints:
  * quantities are positive integers and origin != destination
  * a station cannot send more bikes than it currently has (outflow <= bikes)
  * a station cannot receive past its capacity (final <= capacity)
  * final inventory is non-negative
  * total moved bikes respect the vehicle-capacity limit
"""

from __future__ import annotations

from dataclasses import dataclass

from .problem import RebalancingPlan, RebalancingProblem


@dataclass(frozen=True)
class FeasibilityReport:
    feasible: bool
    violations: tuple[str, ...]

    @property
    def reason(self) -> str | None:
        return None if self.feasible else "; ".join(self.violations)


def check_feasibility(problem: RebalancingProblem, plan: RebalancingPlan) -> FeasibilityReport:
    violations: list[str] = []
    known = {s.station_id for s in problem.stations}

    # Per-station outflow (only bikes present at the origin may leave, section 14.1).
    outflow: dict[str, int] = {s.station_id: 0 for s in problem.stations}
    for m in plan.moves:
        if m.origin_id not in known or m.destination_id not in known:
            violations.append(f"move references unknown station {m.origin_id}->{m.destination_id}")
            continue
        if m.origin_id == m.destination_id:
            violations.append(f"{m.origin_id}: origin and destination are the same")
        if not isinstance(m.quantity, int) or m.quantity <= 0:
            violations.append(
                f"{m.origin_id}->{m.destination_id}: quantity {m.quantity} must be a positive int"
            )
            continue
        outflow[m.origin_id] += m.quantity

    for s in problem.stations:
        if outflow[s.station_id] > s.bikes:
            violations.append(
                f"{s.station_id}: outflow {outflow[s.station_id]} exceeds available bikes {s.bikes}"
            )

    final = plan.final_inventory(problem)
    for s in problem.stations:
        f = final[s.station_id]
        if f < 0:
            violations.append(f"{s.station_id}: final inventory {f} is negative")
        if f > s.capacity:
            violations.append(f"{s.station_id}: final inventory {f} exceeds capacity {s.capacity}")

    if plan.total_moved > problem.vehicle_capacity:
        violations.append(
            f"total moved {plan.total_moved} exceeds vehicle capacity {problem.vehicle_capacity}"
        )

    return FeasibilityReport(feasible=not violations, violations=tuple(violations))

"""Rebalancing problem & plan data model. CLAUDE.md section 14.

Plain, frozen dataclasses (the API boundary uses Pydantic schemas separately, section 6). A
``RebalancingProblem`` is a set of stations with current inventory, capacity, and a desired
(target) level, plus the operational cost weights and a vehicle-capacity limit. A
``RebalancingPlan`` is an ordered set of integer bike moves between stations.

Geometry note: distances are great-circle kilometres via the shared ``haversine_km`` kernel
(``pipelines.features.kernels``) so the optimization layer reuses one distance definition.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config.rebalancing import RebalancingCosts
from pipelines.features.kernels import haversine_km


@dataclass(frozen=True)
class Station:
    """A dock station with current and desired inventory.

    Invariants (validated on construction): ``0 <= bikes <= capacity`` and
    ``0 <= target <= capacity``, all non-negative integers.
    """

    station_id: str
    name: str
    lat: float
    lng: float
    bikes: int  # current bikes available
    capacity: int  # total docks (bikes + empty docks)
    target: int  # desired bikes to serve the forecast horizon
    zone_id: str | None = None

    def __post_init__(self) -> None:
        if self.capacity < 0:
            raise ValueError(f"{self.station_id}: capacity must be >= 0")
        if not (0 <= self.bikes <= self.capacity):
            raise ValueError(f"{self.station_id}: bikes {self.bikes} out of [0, {self.capacity}]")
        if not (0 <= self.target <= self.capacity):
            raise ValueError(f"{self.station_id}: target {self.target} out of [0, {self.capacity}]")

    @property
    def surplus(self) -> int:
        """Bikes above target that could be given away (>= 0)."""
        return max(0, self.bikes - self.target)

    @property
    def deficit(self) -> int:
        """Bikes below target that are needed (>= 0)."""
        return max(0, self.target - self.bikes)

    @property
    def dock_room(self) -> int:
        """Bikes that can still be received before hitting capacity."""
        return self.capacity - self.bikes


@dataclass(frozen=True)
class Move:
    """An integer relocation of ``quantity`` bikes from one station to another."""

    origin_id: str
    destination_id: str
    quantity: int
    distance_km: float


@dataclass(frozen=True)
class RebalancingProblem:
    stations: tuple[Station, ...]
    costs: RebalancingCosts = field(default_factory=RebalancingCosts)
    vehicle_capacity: int = 18

    def __post_init__(self) -> None:
        ids = [s.station_id for s in self.stations]
        if len(ids) != len(set(ids)):
            raise ValueError("station ids must be unique")
        if self.vehicle_capacity < 0:
            raise ValueError("vehicle_capacity must be >= 0")

    def index_of(self, station_id: str) -> int:
        for i, s in enumerate(self.stations):
            if s.station_id == station_id:
                return i
        raise KeyError(station_id)

    def distance_km(self, i: int, j: int) -> float:
        a, b = self.stations[i], self.stations[j]
        return haversine_km(a.lat, a.lng, b.lat, b.lng)


@dataclass(frozen=True)
class RebalancingPlan:
    """A set of moves plus the solver that produced it. Feasibility is checked separately."""

    moves: tuple[Move, ...]
    solver: str

    @property
    def total_moved(self) -> int:
        return sum(m.quantity for m in self.moves)

    def final_inventory(self, problem: RebalancingProblem) -> dict[str, int]:
        """Bikes at each station after applying the plan."""
        final = {s.station_id: s.bikes for s in problem.stations}
        for m in self.moves:
            final[m.origin_id] -= m.quantity
            final[m.destination_id] += m.quantity
        return final

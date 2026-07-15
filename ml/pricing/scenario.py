"""Simulated demand scenario for policy simulation (V1_Prompt §16).

Built from the curated rebalancing fixture so it lines up with the rest of the demo: quiet zones
hold surplus bikes; the event-exposed zones have raised rent demand and go into deficit. This is a
**labelled simulated scenario**, not measured demand (invariant 5/10).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pipelines.features.zones import zone_for

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = _ROOT / "data" / "fixtures" / "rebalancing_demo.json"

# Demo event uplift (extra expected departures in event-exposed zones), matching the rebalancing
# golden path. Keyed by station id. Quiet zones get 0.
DEMO_EVENT_UPLIFT: dict[str, int] = {"JC_HOBOKEN": 2, "JC_CITYHALL": 4, "JC_NEWPORT": 2}

# The controlled Jersey City / Hoboken demo scenario: two quiet donor zones (Grove, Exchange) plus
# the three event-exposed deficit zones. The switchback experiment + pricing policy *simulation*
# runs on this stable set (always present in the fixture), decoupled from the real operational
# network so the labelled simulation stays deterministic regardless of an imported live network.
DEMO_SCENARIO_STATIONS: frozenset[str] = frozenset(
    {"JC_GROVE", "JC_EXCHANGE", "JC_HOBOKEN", "JC_CITYHALL", "JC_NEWPORT"}
)


@dataclass(frozen=True)
class ScenarioStation:
    station_id: str
    zone_id: str
    lat: float
    lng: float
    bikes: int
    capacity: int
    base_target: int
    rent_demand: int  # expected riders wanting to RENT over the horizon
    return_demand: int  # expected riders wanting to RETURN over the horizon

    @property
    def free_docks(self) -> int:
        return max(0, self.capacity - self.bikes)


def build_demo_scenario(event_uplift: dict[str, int] | None = None) -> list[ScenarioStation]:
    """Load the fixture and synthesise rent/return demand. Deterministic (invariant 14)."""
    uplift = DEMO_EVENT_UPLIFT if event_uplift is None else event_uplift
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    stations: list[ScenarioStation] = []
    for s in payload["stations"]:
        if s["station_id"] not in DEMO_SCENARIO_STATIONS:
            continue  # controlled demo scenario only (decoupled from any imported live network)
        base = int(s["base_target"])
        extra = int(uplift.get(s["station_id"], 0))
        # Rent demand tracks the (event-adjusted) target; return demand is the baseline arrivals.
        rent_demand = base + extra
        return_demand = base
        stations.append(
            ScenarioStation(
                station_id=s["station_id"],
                zone_id=zone_for(float(s["lat"]), float(s["lng"])),
                lat=float(s["lat"]),
                lng=float(s["lng"]),
                bikes=int(s["bikes_available"]),
                capacity=int(s["capacity"]),
                base_target=base,
                rent_demand=rent_demand,
                return_demand=return_demand,
            )
        )
    return stations

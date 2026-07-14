"""Versioned deterministic choice simulator (V1_Prompt §16).

Simulates rider pickup/return choices under station credits and optional recommendation steering,
so competing policies can be compared. This is a **simulator** — every outcome is
``is_simulated=true`` and never a live business result (invariant 10). No RL/bandit; a fixed,
seeded rule. Budget is a hard cap on incentive spend; credits are >= 0 (no surcharge).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import StrEnum

from config.pricing import PricingConfig
from pipelines.features.kernels import haversine_km

from .scenario import ScenarioStation


class RiderKind(StrEnum):
    RENT = "rent"
    RETURN = "return"


@dataclass(frozen=True)
class Rider:
    kind: RiderKind
    origin_lat: float
    origin_lng: float
    home_zone: str


@dataclass
class SimOutcome:
    total_rent_demand: int
    total_return_demand: int
    fulfilled_rent: int = 0
    fulfilled_return: int = 0
    shortage_events: int = 0  # RENT riders who found no feasible bike within detour
    overflow_events: int = 0  # RETURN riders who found no feasible dock within detour
    incentive_spend: float = 0.0
    total_detour_km: float = 0.0
    n_choices: int = 0
    budget_exhausted: bool = False
    per_zone_demand: dict[str, int] = field(default_factory=dict)
    per_zone_fulfilled: dict[str, int] = field(default_factory=dict)
    is_simulated: bool = True

    @property
    def total_demand(self) -> int:
        return self.total_rent_demand + self.total_return_demand

    @property
    def fulfilled(self) -> int:
        return self.fulfilled_rent + self.fulfilled_return


def _riders(stations: list[ScenarioStation]) -> list[Rider]:
    riders: list[Rider] = []
    for st in stations:
        for _ in range(st.rent_demand):
            riders.append(Rider(RiderKind.RENT, st.lat, st.lng, st.zone_id))
        for _ in range(st.return_demand):
            riders.append(Rider(RiderKind.RETURN, st.lat, st.lng, st.zone_id))
    return riders


class ChoiceSimulator:
    """Deterministic given (stations, credits, config.seed). Mutates a *copy* of inventory."""

    def __init__(self, config: PricingConfig | None = None) -> None:
        self.cfg = config or PricingConfig()

    def run(
        self,
        stations: list[ScenarioStation],
        credits: dict[str, float] | None = None,
        recommend: bool = False,
    ) -> SimOutcome:
        cfg = self.cfg
        credits = credits or {}
        # Reject any negative credit up front (no surcharge, §16).
        if any(c < 0 for c in credits.values()):
            raise ValueError("credits must be >= 0 (no surcharge, V1_Prompt §16)")

        bikes = {s.station_id: s.bikes for s in stations}
        docks = {s.station_id: s.free_docks for s in stations}
        out = SimOutcome(
            total_rent_demand=sum(s.rent_demand for s in stations),
            total_return_demand=sum(s.return_demand for s in stations),
        )
        for s in stations:
            out.per_zone_demand[s.zone_id] = out.per_zone_demand.get(s.zone_id, 0) + (
                s.rent_demand + s.return_demand
            )

        rng = random.Random(cfg.seed)
        riders = _riders(stations)
        rng.shuffle(riders)

        for r in riders:
            out.n_choices += 1
            nearest = min(
                stations, key=lambda st: haversine_km(r.origin_lat, r.origin_lng, st.lat, st.lng)
            )
            near_d = haversine_km(r.origin_lat, r.origin_lng, nearest.lat, nearest.lng)

            feasible = []
            for st in stations:
                have = bikes[st.station_id] if r.kind == RiderKind.RENT else docks[st.station_id]
                detour = haversine_km(r.origin_lat, r.origin_lng, st.lat, st.lng) - near_d
                if have > 0 and detour <= cfg.max_detour_km:
                    feasible.append(st)
            if not feasible:
                if r.kind == RiderKind.RENT:
                    out.shortage_events += 1
                else:
                    out.overflow_events += 1
                continue

            chosen = self._choose(r, feasible, credits, recommend, rng, near_d)
            # Fulfil.
            if r.kind == RiderKind.RENT:
                bikes[chosen.station_id] -= 1
                out.fulfilled_rent += 1
            else:
                docks[chosen.station_id] -= 1
                out.fulfilled_return += 1
            out.per_zone_fulfilled[r.home_zone] = out.per_zone_fulfilled.get(r.home_zone, 0) + 1
            out.total_detour_km += max(
                0.0, haversine_km(r.origin_lat, r.origin_lng, chosen.lat, chosen.lng) - near_d
            )
            # Pay the credit (hard budget cap).
            credit = credits.get(chosen.station_id, 0.0)
            if credit > 0:
                remaining = cfg.incentive_budget - out.incentive_spend
                if remaining <= 0:
                    out.budget_exhausted = True
                else:
                    out.incentive_spend += min(credit, remaining)
        return out

    def _choose(self, r, feasible, credits, recommend, rng, near_d):
        # Recommendation steering: a compliant fraction picks the best-stocked feasible station.
        if recommend and rng.random() < self.cfg.recommendation_compliance:
            return max(feasible, key=lambda st: st.capacity)  # steer toward high-capacity balancers
        # Otherwise utility = -distance + incentive_weight * credit.
        def utility(st: ScenarioStation) -> float:
            d = haversine_km(r.origin_lat, r.origin_lng, st.lat, st.lng)
            return -d + self.cfg.incentive_weight * credits.get(st.station_id, 0.0)

        return max(feasible, key=utility)

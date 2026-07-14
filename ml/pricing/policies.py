"""Policies P0-P5 and their simulated metric bundle (V1_Prompt §16).

Each policy sets (truck moves, station credits, recommendation steering); the choice simulator then
produces the outcome. Constraints honoured: inventory & capacity (simulator), budget (hard cap),
max detour (simulator), fairness measured by zone (never protected attributes), credits >= 0 (no
surcharge). Every result is ``is_simulated=true`` with the disclaimer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from config.pricing import SIMULATED_DISCLAIMER, PolicySpec, PricingConfig
from config.rebalancing import RebalancingCosts
from optimization.classical.greedy import greedy_plan
from optimization.classical.problem import RebalancingProblem
from optimization.classical.problem import Station as OptStation

from .scenario import ScenarioStation
from .simulator import ChoiceSimulator, SimOutcome

# Modeled minutes of service impact per unmet pickup/return (documented proxy, not measured).
MIN_PER_UNMET = 10.0


@dataclass(frozen=True)
class PolicySimResult:
    policy_key: str
    policy_label: str
    fulfilled_demand_rate: float
    shortage_minutes: float
    overflow_minutes: float
    truck_bike_km: float
    incentive_spend: float
    net_operating_cost: float
    avg_detour_km: float
    service_disparity: float  # fairness gap across zones (higher = less fair)
    budget_exhausted: bool
    is_simulated: bool = True
    disclaimer: str = SIMULATED_DISCLAIMER

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        return d


def _apply_truck(stations: list[ScenarioStation]) -> tuple[list[ScenarioStation], float]:
    """Greedy rebalancing toward rent demand; returns updated stations + truck bike-km."""
    opt = [
        OptStation(
            station_id=s.station_id, name=s.station_id, lat=s.lat, lng=s.lng,
            bikes=s.bikes, capacity=s.capacity, target=s.rent_demand, zone_id=s.zone_id,
        )
        for s in stations
    ]
    problem = RebalancingProblem(stations=tuple(opt), costs=RebalancingCosts(), vehicle_capacity=18)
    plan = greedy_plan(problem)
    delta: dict[str, int] = {}
    km = 0.0
    for m in plan.moves:
        delta[m.origin_id] = delta.get(m.origin_id, 0) - m.quantity
        delta[m.destination_id] = delta.get(m.destination_id, 0) + m.quantity
        km += m.distance_km * m.quantity
    updated = [replace(s, bikes=max(0, s.bikes + delta.get(s.station_id, 0))) for s in stations]
    return updated, round(km, 4)


def _dynamic_credits(
    stations: list[ScenarioStation], cfg: PricingConfig, static: bool
) -> dict[str, float]:
    """Offer pickup credits at surplus stations to pull rent demand off deficit stations.

    ``static`` uses a single flat tier; dynamic scales the tier by the surplus magnitude
    (event-aware, since event zones drive the deficits). Credits use the allowed tiers only.
    """
    tiers = sorted(cfg.credit_tiers)
    credits: dict[str, float] = {}
    for s in stations:
        surplus = s.bikes - s.rent_demand
        if surplus <= 0:
            continue
        if static:
            credits[s.station_id] = tiers[1] if len(tiers) > 1 else tiers[0]  # flat 0.5
        else:
            # More surplus -> higher tier (index grows with surplus), capped at the top tier.
            idx = min(len(tiers) - 1, 1 + surplus // 3)
            credits[s.station_id] = tiers[idx]
    return credits


def run_policy(
    spec: PolicySpec, stations: list[ScenarioStation], cfg: PricingConfig | None = None
) -> PolicySimResult:
    cfg = cfg or PricingConfig()
    truck_km = 0.0
    working = stations
    if spec.truck:
        working, truck_km = _apply_truck(stations)

    credits: dict[str, float] = {}
    if spec.credit == "static":
        credits = _dynamic_credits(working, cfg, static=True)
    elif spec.credit == "dynamic":
        credits = _dynamic_credits(working, cfg, static=False)

    out = ChoiceSimulator(cfg).run(working, credits=credits, recommend=spec.recommend)
    return _metrics(spec, out, truck_km, cfg)


def _metrics(
    spec: PolicySpec, out: SimOutcome, truck_km: float, cfg: PricingConfig
) -> PolicySimResult:
    total = max(1, out.total_demand)
    shortage_min = out.shortage_events * MIN_PER_UNMET
    overflow_min = out.overflow_events * MIN_PER_UNMET
    net_cost = (
        cfg.shortage_cost * out.shortage_events
        + cfg.overflow_cost * out.overflow_events
        + cfg.distance_cost * truck_km
        + cfg.incentive_cost * out.incentive_spend
    )
    # Fairness: gap between best- and worst-served zones (unfulfilled rate).
    rates = []
    for zone, dem in out.per_zone_demand.items():
        if dem > 0:
            unfulfilled = 1.0 - out.per_zone_fulfilled.get(zone, 0) / dem
            rates.append(unfulfilled)
    disparity = (max(rates) - min(rates)) if rates else 0.0
    return PolicySimResult(
        policy_key=spec.key,
        policy_label=spec.label,
        fulfilled_demand_rate=round(out.fulfilled / total, 4),
        shortage_minutes=round(shortage_min, 2),
        overflow_minutes=round(overflow_min, 2),
        truck_bike_km=round(truck_km, 4),
        incentive_spend=round(out.incentive_spend, 4),
        net_operating_cost=round(net_cost, 4),
        avg_detour_km=round(out.total_detour_km / max(1, out.n_choices), 4),
        service_disparity=round(disparity, 4),
        budget_exhausted=out.budget_exhausted,
    )

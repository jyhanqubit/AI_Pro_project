"""Simulated revenue comparison for event-aware dynamic fare (V2-05). CLAUDE.md §14, §22.

Compares two fare policies over the same as-of station state:

* **flat** — every station charges the base fare (multiplier 1.00);
* **event-aware dynamic** — the bounded scarcity surcharge from :mod:`ml.pricing.dynamic`
  (base fare in surplus/quiet zones, a capped surcharge only where the event drives scarcity).

The kernel here is pure: it takes each station's model demand estimate, available bikes, and the
already-computed dynamic :class:`~ml.pricing.dynamic.PriceQuote`, and turns them into revenue under
an explicit demand-elasticity response. It is decoupled from both the scenario fixture and the
replay engine so it is trivially testable; :mod:`ml.pricing.revenue_eval` feeds it the *real*
shipped quotes from the replay path (never a hand-built surcharge).

Every figure is a **SIMULATED SHADOW** result: no real rider is charged and there is no real
conversion log (V2 invariant, CLAUDE.md §22). A surcharge is not free money — a fraction of riders
balk as price rises. A revenue uplift is only reported when the bounded surcharge's price gain
survives that modeled conversion loss. The economic reason it does at event zones: those stations
are supply-constrained (fewer bikes than riders), so even after some riders balk, demand still
exceeds the few available bikes — the surcharge captures value on bikes that would have sold anyway.
The elasticity assumption is explicit and swept (:func:`elasticity_sweep`) so the boundary where the
uplift disappears is reported, never hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dynamic import PriceQuote


def conversion_factor(multiplier: float, elasticity: float) -> float:
    """Fraction of would-be renters who still rent at a given fare multiplier.

    A documented linear demand curve: ``1 - elasticity * (multiplier - 1)``, clamped to [0, 1].
    ``elasticity`` is the sensitivity of demand to price (0 = perfectly inelastic; 1.0 means a
    +100% fare would remove all demand). At the base fare (multiplier 1.0) conversion is always 1.0.
    """
    if elasticity < 0:
        raise ValueError("elasticity must be >= 0")
    factor = 1.0 - elasticity * (multiplier - 1.0)
    return 0.0 if factor < 0.0 else 1.0 if factor > 1.0 else factor


@dataclass(frozen=True)
class StationDemand:
    """One station's as-of demand/supply for the revenue simulation."""

    station_id: str
    zone_id: str
    base_demand: float  # would-be renters at base fare (the shipped model's demand estimate)
    available_bikes: int


@dataclass(frozen=True)
class StationRevenue:
    station_id: str
    zone_id: str
    multiplier: float
    final_price: float
    would_be_renters: int  # base demand after the elasticity conversion drop
    available_bikes: int
    fulfilled_rentals: int  # min(would_be_renters, available_bikes) — supply cap
    unmet_rentals: int
    revenue: float
    tier_reason: str


def _station_revenue(
    demand: StationDemand, *, multiplier: float, final_price: float, elasticity: float, reason: str
) -> StationRevenue:
    conv = conversion_factor(multiplier, elasticity)
    would_be = int(round(demand.base_demand * conv))
    fulfilled = min(would_be, demand.available_bikes)
    return StationRevenue(
        station_id=demand.station_id,
        zone_id=demand.zone_id,
        multiplier=multiplier,
        final_price=final_price,
        would_be_renters=would_be,
        available_bikes=demand.available_bikes,
        fulfilled_rentals=fulfilled,
        unmet_rentals=max(0, would_be - fulfilled),
        revenue=round(fulfilled * final_price, 4),
        tier_reason=reason,
    )


@dataclass(frozen=True)
class PolicyRevenue:
    policy: str  # "flat" | "event_aware_dynamic"
    total_revenue: float
    total_fulfilled: int
    total_unmet: int
    revenue_per_rental: float
    surcharged_stations: int
    stations: list[StationRevenue]


def _aggregate(policy: str, rows: list[StationRevenue]) -> PolicyRevenue:
    revenue = round(sum(r.revenue for r in rows), 4)
    fulfilled = sum(r.fulfilled_rentals for r in rows)
    unmet = sum(r.unmet_rentals for r in rows)
    return PolicyRevenue(
        policy=policy,
        total_revenue=revenue,
        total_fulfilled=fulfilled,
        total_unmet=unmet,
        revenue_per_rental=round(revenue / fulfilled, 4) if fulfilled else 0.0,
        surcharged_stations=sum(1 for r in rows if r.multiplier > 1.0),
        stations=rows,
    )


@dataclass(frozen=True)
class RevenueComparison:
    elasticity: float
    flat: PolicyRevenue
    dynamic: PolicyRevenue
    revenue_uplift: float  # dynamic - flat (absolute, simulated units)
    revenue_uplift_pct: float
    fulfilled_delta: int  # dynamic - flat (rentals lost to the surcharge, if any)


def compare_revenue(
    lines: list[tuple[StationDemand, PriceQuote]], *, elasticity: float
) -> RevenueComparison:
    """Flat vs event-aware dynamic revenue for the same stations at one elasticity.

    ``lines`` pairs each station's demand with its shipped dynamic quote. The flat policy re-prices
    the identical stations at the quote's base fare (multiplier 1.0). Deterministic (invariant 14).
    """
    flat_rows: list[StationRevenue] = []
    dyn_rows: list[StationRevenue] = []
    for demand, q in lines:
        flat_rows.append(
            _station_revenue(
                demand,
                multiplier=1.0,
                final_price=q.base_fare,
                elasticity=elasticity,
                reason="base",
            )
        )
        dyn_rows.append(
            _station_revenue(
                demand,
                multiplier=q.tier_multiplier,
                final_price=q.final_price,
                elasticity=elasticity,
                reason=q.tier_reason,
            )
        )
    flat = _aggregate("flat", flat_rows)
    dyn = _aggregate("event_aware_dynamic", dyn_rows)
    uplift = round(dyn.total_revenue - flat.total_revenue, 4)
    pct = round(100.0 * uplift / flat.total_revenue, 2) if flat.total_revenue else 0.0
    return RevenueComparison(
        elasticity=round(elasticity, 4),
        flat=flat,
        dynamic=dyn,
        revenue_uplift=uplift,
        revenue_uplift_pct=pct,
        fulfilled_delta=dyn.total_fulfilled - flat.total_fulfilled,
    )


def elasticity_sweep(
    lines: list[tuple[StationDemand, PriceQuote]],
    *,
    elasticities: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5),
) -> list[RevenueComparison]:
    """Sweep the elasticity assumption so the boundary where the uplift disappears is visible."""
    return [compare_revenue(lines, elasticity=e) for e in elasticities]

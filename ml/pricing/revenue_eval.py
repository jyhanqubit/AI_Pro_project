"""Run the event-aware dynamic-fare **revenue** comparison and write the report (V2-05).

    python -m ml.pricing.revenue_eval   # -> reports/v2/pricing/revenue_sim.json (+ .md)

Flat base fare vs the bounded event-aware scarcity surcharge, priced with the **real shipped quote
path**: the replay engine is advanced past the curated event, ``station_views`` gives each station's
as-of inventory and demo-heuristic demand delta, and ``price_quote`` produces the identical quote
the ``/v2/pricing/quote`` endpoint serves. Only the revenue/elasticity layer is added on top.

Every figure is a SIMULATED SHADOW result — not a live price, no rider charged, no real conversion
log (CLAUDE.md §22, V2 invariants). The demand-elasticity assumption is explicit and swept, so the
boundary where the uplift disappears is reported, never hidden.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from config.pricing_v2 import SIMULATED_DISCLAIMER, DynamicFareConfig
from contracts.enums import OperatingMode
from ml.pricing.dynamic import PriceQuote, price_quote
from ml.pricing.revenue import (
    RevenueComparison,
    StationDemand,
    compare_revenue,
    elasticity_sweep,
)
from services.api.replay import ReplayEngine
from services.api.v2 import station_views

_ROOT = Path(__file__).resolve().parents[2]
_OUT = _ROOT / "reports" / "v2" / "pricing" / "revenue_sim.json"
_OUT_MD = _OUT.with_suffix(".md")

# Advance past the curated concert/transit events so the demo-heuristic demand delta is live.
POST_EVENT_CUTOFF = datetime.fromisoformat("2026-07-12T15:30:00-04:00")

# Moderate reference elasticity for the headline figure (a +100% fare would remove ~50% of demand).
# The full sweep reports how the uplift changes as this assumption moves.
REFERENCE_ELASTICITY = 0.5


def build_lines(
    engine: ReplayEngine,
    cutoff: datetime,
    cfg: DynamicFareConfig,
    *,
    severity: float = 1.0,
    disabled_event_ids: tuple[str, ...] = (),
) -> list[tuple[StationDemand, PriceQuote]]:
    """Pair each station's as-of demand with its shipped dynamic quote (the real pricing path).

    ``severity`` (>= 1) is an explicit **what-if** amplifier on the *event* component only: it
    scales the demo-heuristic demand delta and the event-driven part of the target
    (``target - base_target``) to model a stronger version of the same event. ``severity == 1.0``
    reproduces the shipped quote exactly. Base inventory scarcity is never amplified.

    ``disabled_event_ids`` turns the named events off before forecasting, so the demand delta,
    targets and thus the surcharge reflect a scenario without those events (operator event-toggle).
    """
    views = station_views(engine, cutoff, disabled_event_ids)
    events = engine.available_events(cutoff, disabled_event_ids)
    from config.pricing_v2 import NO_SURCHARGE_EVENT_TYPES

    safety_block = any(str(e.event_type) in NO_SURCHARGE_EVENT_TYPES for e in events)
    total_surplus = sum(max(0, v.surplus) for v in views)

    lines: list[tuple[StationDemand, PriceQuote]] = []
    for v in views:
        event_uplift = max(0, v.target - v.base_target)  # event-driven part of the target
        scaled_target = v.base_target + int(round(event_uplift * severity))
        scaled_delta = round(v.demand_delta * severity, 4)
        q = price_quote(
            bikes=v.bikes,
            target=scaled_target,
            capacity=v.capacity,
            surplus=v.bikes - scaled_target,
            demand_delta=scaled_delta,
            neighbor_spare=float(total_surplus - max(0, v.surplus)),
            stale=False,
            safety_block=safety_block,
            cfg=cfg,
        )
        # Would-be renters at base fare = the station's own event-adjusted demand target (per
        # station, so a zone forecast is not triple-counted across its stations). ``target``
        # already folds in the demo-heuristic event uplift; available bikes cap actual rentals.
        demand = StationDemand(
            station_id=v.station_id,
            zone_id=v.zone_id,
            base_demand=float(max(0, scaled_target)),
            available_bikes=v.bikes,
        )
        lines.append((demand, q))
    return lines


def _comparison_dict(c: RevenueComparison, *, include_stations: bool = False) -> dict:
    def _policy(p) -> dict:
        d = {
            "policy": p.policy,
            "total_revenue": p.total_revenue,
            "total_fulfilled": p.total_fulfilled,
            "total_unmet": p.total_unmet,
            "revenue_per_rental": p.revenue_per_rental,
            "surcharged_stations": p.surcharged_stations,
        }
        if include_stations:
            d["stations"] = [
                {
                    "station_id": s.station_id,
                    "zone_id": s.zone_id,
                    "multiplier": s.multiplier,
                    "final_price": s.final_price,
                    "would_be_renters": s.would_be_renters,
                    "available_bikes": s.available_bikes,
                    "fulfilled_rentals": s.fulfilled_rentals,
                    "unmet_rentals": s.unmet_rentals,
                    "revenue": s.revenue,
                    "tier_reason": s.tier_reason,
                }
                for s in p.stations
                if s.multiplier > 1.0 or s.revenue > 0
            ]
        return d

    return {
        "elasticity": c.elasticity,
        "flat": _policy(c.flat),
        "event_aware_dynamic": _policy(c.dynamic),
        "revenue_uplift": c.revenue_uplift,
        "revenue_uplift_pct": c.revenue_uplift_pct,
        "fulfilled_delta": c.fulfilled_delta,
    }


def _markdown(
    cfg: DynamicFareConfig,
    headline: RevenueComparison,
    sweep: list[RevenueComparison],
    severity_rows: list[dict],
    n: int,
) -> str:
    lines = [
        "# V2-05 — Event-aware dynamic-fare revenue (SIMULATED SHADOW)",
        "",
        f"> {SIMULATED_DISCLAIMER}. No rider is charged; there is no real conversion log. Revenue",
        "> is modeled through an explicit demand-elasticity response and reported honestly, with",
        "> the elasticity boundary where the uplift disappears.",
        "",
        f"- Config `{cfg.version}` · base fare **{cfg.base_fare:.2f}** · "
        f"cap **{cfg.max_multiplier:.2f}×**",
        f"- Priced with the real `/v2/pricing/quote` path (replay engine as-of "
        f"`{POST_EVENT_CUTOFF.isoformat()}`, {n} stations)",
        f"- Headline elasticity **{REFERENCE_ELASTICITY}** "
        f"(a +100% fare would remove ~{int(REFERENCE_ELASTICITY * 100)}% of demand)",
        "",
        "## Headline",
        "",
        "| policy | revenue | fulfilled rentals | rev / rental | surcharged stations |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| flat (base fare) | {headline.flat.total_revenue:.2f} | "
        f"{headline.flat.total_fulfilled} | {headline.flat.revenue_per_rental:.3f} | "
        f"{headline.flat.surcharged_stations} |",
        f"| event-aware dynamic | {headline.dynamic.total_revenue:.2f} | "
        f"{headline.dynamic.total_fulfilled} | {headline.dynamic.revenue_per_rental:.3f} | "
        f"{headline.dynamic.surcharged_stations} |",
        "",
        f"**Revenue uplift {headline.revenue_uplift:+.2f} "
        f"({headline.revenue_uplift_pct:+.1f}%)** · fulfilled-rental delta "
        f"{headline.fulfilled_delta:+d} (rentals lost to the surcharge at this elasticity).",
        "",
        "## Elasticity sensitivity",
        "",
        "The uplift is only real while the bounded surcharge's price gain survives the modeled",
        "conversion loss. Higher elasticity = riders balk sooner.",
        "",
        "| elasticity | flat revenue | dynamic revenue | uplift | uplift % | fulfilled Δ |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for c in sweep:
        lines.append(
            f"| {c.elasticity:.2f} | {c.flat.total_revenue:.2f} | "
            f"{c.dynamic.total_revenue:.2f} | {c.revenue_uplift:+.2f} | "
            f"{c.revenue_uplift_pct:+.1f}% | {c.fulfilled_delta:+d} |"
        )
    lines += [
        "",
        "Reading: the surcharge only fires at the event-affected zones, and there the available",
        "bikes are fewer than the riders who want them (supply-constrained), so the surcharge",
        "captures value on bikes that would have sold anyway. The uplift stays positive until the",
        "elasticity is high enough that the surcharge pushes converted demand below the available",
        "supply — that crossover is the honest limit of the claim.",
        "",
        "## Event-severity what-if",
        "",
        "How event-aware revenue scales as the **event** intensifies (event component only; base",
        "inventory scarcity is not amplified). This is a labelled what-if, not a measured event.",
        "",
        "| event severity | flat rev | dynamic rev | uplift | uplift % | max tier | surcharged |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in severity_rows:
        lines.append(
            f"| ×{r['severity']:.0f} | {r['flat_revenue']:.2f} | {r['dynamic_revenue']:.2f} | "
            f"{r['revenue_uplift']:+.2f} | {r['revenue_uplift_pct']:+.1f}% | "
            f"{r['max_tier_multiplier']:.2f}× | {r['surcharged_stations']} |"
        )
    lines += [
        "",
        "As the event grows, more zones cross into scarcity and the bounded surcharge climbs its",
        "tiers (toward the hard 1.50× cap), so event-aware revenue rises with event intensity as",
        "flat pricing leaves that value on the table. This is the event-awareness of the pricing,",
        "shown directly.",
        "",
    ]
    return "\n".join(lines)


SEVERITY_FACTORS: tuple[float, ...] = (1.0, 2.0, 3.0)


def main() -> int:
    cfg = DynamicFareConfig()
    engine = ReplayEngine(OperatingMode.HISTORICAL_REPLAY)
    engine.set_cutoff(POST_EVENT_CUTOFF)
    lines = build_lines(engine, POST_EVENT_CUTOFF, cfg)

    headline = compare_revenue(lines, elasticity=REFERENCE_ELASTICITY)
    sweep = elasticity_sweep(lines)

    # What-if: how event-aware revenue scales as the *event* intensifies (event component only).
    severity_rows = []
    for factor in SEVERITY_FACTORS:
        s_lines = build_lines(engine, POST_EVENT_CUTOFF, cfg, severity=factor)
        s_cmp = compare_revenue(s_lines, elasticity=REFERENCE_ELASTICITY)
        max_tier = max((r.multiplier for r in s_cmp.dynamic.stations), default=1.0)
        severity_rows.append(
            {
                "severity": factor,
                "flat_revenue": s_cmp.flat.total_revenue,
                "dynamic_revenue": s_cmp.dynamic.total_revenue,
                "revenue_uplift": s_cmp.revenue_uplift,
                "revenue_uplift_pct": s_cmp.revenue_uplift_pct,
                "surcharged_stations": s_cmp.dynamic.surcharged_stations,
                "max_tier_multiplier": round(max_tier, 4),
                "fulfilled_delta": s_cmp.fulfilled_delta,
            }
        )

    payload = {
        "mode": "policy_simulation",
        "is_simulated": True,
        "disclaimer": SIMULATED_DISCLAIMER,
        "config_version": cfg.version,
        "base_fare": cfg.base_fare,
        "max_multiplier": cfg.max_multiplier,
        "cutoff": POST_EVENT_CUTOFF.isoformat(),
        "reference_elasticity": REFERENCE_ELASTICITY,
        "scenario": {"n_stations": len(lines)},
        "headline": _comparison_dict(headline, include_stations=True),
        "elasticity_sweep": [_comparison_dict(c) for c in sweep],
        "event_severity_whatif": severity_rows,
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _OUT_MD.write_text(_markdown(cfg, headline, sweep, severity_rows, len(lines)), encoding="utf-8")

    print(f"SIMULATED dynamic-fare revenue (base={cfg.base_fare}, cap={cfg.max_multiplier}×)")
    print(f"  priced via the real replay path, cutoff {POST_EVENT_CUTOFF.isoformat()}")
    print(f"  headline elasticity = {REFERENCE_ELASTICITY}")
    print(
        f"  flat revenue      {headline.flat.total_revenue:8.2f} "
        f"({headline.flat.total_fulfilled} rentals)"
    )
    print(
        f"  dynamic revenue   {headline.dynamic.total_revenue:8.2f} "
        f"({headline.dynamic.total_fulfilled} rentals, "
        f"{headline.dynamic.surcharged_stations} surcharged)"
    )
    print(
        f"  uplift            {headline.revenue_uplift:+8.2f} "
        f"({headline.revenue_uplift_pct:+.1f}%), fulfilled Δ {headline.fulfilled_delta:+d}"
    )
    print("  elasticity sweep:")
    for c in sweep:
        print(
            f"    e={c.elasticity:.2f}  uplift {c.revenue_uplift:+7.2f} "
            f"({c.revenue_uplift_pct:+5.1f}%)  fulfilled Δ {c.fulfilled_delta:+d}"
        )
    print("  event-severity what-if:")
    for r in severity_rows:
        print(
            f"    ×{r['severity']:.0f}  dynamic {r['dynamic_revenue']:8.2f}  "
            f"uplift {r['revenue_uplift']:+7.2f} ({r['revenue_uplift_pct']:+5.1f}%)  "
            f"max tier {r['max_tier_multiplier']:.2f}×  surcharged {r['surcharged_stations']}"
        )
    print(f"wrote {_OUT.relative_to(_ROOT)}  (SIMULATED SHADOW — NOT A LIVE PRICE)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

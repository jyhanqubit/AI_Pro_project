"""Dynamic-fare pure kernel (V2-05). CLAUDE.md §14 + V2 invariants.

Pure, deterministic functions that turn a station's as-of scarcity into a bounded surcharge quote
(or a balancing credit when the station is in surplus). No I/O, no randomness, no rider attributes —
the only inputs are inventory/scarcity quantities and config. Same inputs → same quote.

Every quote is a SIMULATED SHADOW quote (see config/pricing_v2.py); the API wrapper labels it and
never applies it to a rider. Guardrails (safety-event → base, stale → base, hard multiplier cap) are
enforced here so they cannot be bypassed by a caller.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.pricing_v2 import DynamicFareConfig


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


@dataclass(frozen=True)
class ScarcityComponents:
    shortage_probability: float
    normalized_gap: float
    event_impact: float
    neighbor_buffer: float


@dataclass(frozen=True)
class PriceQuote:
    scarcity_score: float
    components: ScarcityComponents
    base_fare: float
    tier_multiplier: float
    scarcity_surcharge: float  # base_fare + scarcity_surcharge == final_price (auditable)
    final_price: float
    balancing_credit: float
    stale: bool
    safety_block: bool
    capped: bool
    tier_reason: str  # "scarcity" | "stale" | "safety_no_surcharge" | "base"


def scarcity_components(
    *,
    bikes: int,
    target: int,
    capacity: int,
    demand_delta: float,
    neighbor_spare: float,
    cfg: DynamicFareConfig,
) -> ScarcityComponents:
    """Decompose a station's scarcity into four [0, 1] components (stored for the explanation)."""
    shortage = max(0, target - bikes)
    return ScarcityComponents(
        shortage_probability=_clamp01(shortage / max(1, target)),
        normalized_gap=_clamp01((target - bikes) / max(1, capacity)),
        event_impact=_clamp01(max(0.0, demand_delta) / cfg.event_delta_norm),
        neighbor_buffer=_clamp01(neighbor_spare / cfg.neighbor_norm),
    )


def scarcity_pressure_score(c: ScarcityComponents, cfg: DynamicFareConfig) -> float:
    """Weighted scarcity pressure in [0, 1]; nearby surplus (neighbor_buffer) reduces it."""
    raw = (
        cfg.w_shortage * c.shortage_probability
        + cfg.w_gap * c.normalized_gap
        + cfg.w_event * c.event_impact
        - cfg.w_neighbor * c.neighbor_buffer
    )
    return round(_clamp01(raw), 4)


def select_tier(score: float, cfg: DynamicFareConfig) -> float:
    """Map a pressure score to a bounded surcharge multiplier tier."""
    tier = cfg.tiers[0]
    for i, threshold in enumerate(cfg.tier_thresholds):
        if score >= threshold:
            tier = cfg.tiers[i + 1]
    return min(tier, cfg.max_multiplier)


def price_quote(
    *,
    bikes: int,
    target: int,
    capacity: int,
    surplus: int,
    demand_delta: float,
    neighbor_spare: float,
    stale: bool,
    safety_block: bool,
    cfg: DynamicFareConfig,
) -> PriceQuote:
    """A bounded, guardrailed, deterministic shadow fare quote for one station."""
    components = scarcity_components(
        bikes=bikes,
        target=target,
        capacity=capacity,
        demand_delta=demand_delta,
        neighbor_spare=neighbor_spare,
        cfg=cfg,
    )
    score = scarcity_pressure_score(components, cfg)

    # Guardrails first: stale inventory or a safety/emergency event → base fare, no surcharge.
    if stale:
        tier, reason = 1.0, "stale"
    elif safety_block:
        tier, reason = 1.0, "safety_no_surcharge"
    else:
        raw_tier = select_tier(score, cfg)
        tier = min(raw_tier, cfg.max_multiplier)
        reason = "scarcity" if tier > 1.0 else "base"

    capped = tier >= cfg.max_multiplier
    base = round(cfg.base_fare, 4)
    final = round(base * tier, 4)
    surcharge = round(final - base, 4)  # exact: base + surcharge == final

    # A balancing (pickup) credit only when the station is in surplus and not surcharged.
    credit = 0.0
    if tier == 1.0 and surplus > 0 and target > 0:
        credit = round(min(cfg.max_credit, (surplus / target) * cfg.max_credit), 2)

    return PriceQuote(
        scarcity_score=score,
        components=components,
        base_fare=base,
        tier_multiplier=tier,
        scarcity_surcharge=surcharge,
        final_price=final,
        balancing_credit=credit,
        stale=stale,
        safety_block=safety_block,
        capped=capped,
        tier_reason=reason,
    )

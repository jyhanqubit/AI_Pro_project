"""Dynamic fare (V2) configuration — bounded scarcity surcharge + balancing credit.

V2-05 extends the V1 credit-only incentive with a **bounded scarcity surcharge**. Every quote is a
SIMULATED SHADOW quote: it is never applied to a real rider, and there is no real elasticity /
conversion log, so results are labelled simulated (V2 invariants).

Hard rules encoded here (CLAUDE.md §3, §22 + V2 invariants):
- Surcharge is bounded by ``MAX_MULTIPLIER`` (1.50) — never higher.
- **No surcharge on safety / emergency events** (``NO_SURCHARGE_EVENT_TYPES``): fall back to base.
- **Stale data falls back to the base fare** (never surcharge on stale inventory).
- Pricing depends only on *station scarcity* — never on rider identity, reduced-fare status, or any
  protected attribute (those are never inputs). Fairness is measured across zone/time only.
- A station is either scarce (surcharge) or in surplus (a pickup credit) — never both.
"""

from __future__ import annotations

from dataclasses import dataclass

PRICING_V2_CONFIG_VERSION = "pricing-v2"

SIMULATED_DISCLAIMER = "SIMULATED SHADOW QUOTE — NOT A LIVE PRICE (not applied to any rider)"

# Bounded surcharge multiplier tiers (V2-05). 1.00 = base fare (no surcharge).
SURCHARGE_TIERS: tuple[float, ...] = (1.00, 1.10, 1.25, 1.50)
MAX_MULTIPLIER = 1.50

# Event types that forbid any surcharge (safety/emergency). A quote in an affected zone is base.
NO_SURCHARGE_EVENT_TYPES: frozenset[str] = frozenset({"SAFETY_INCIDENT"})


@dataclass(frozen=True)
class DynamicFareConfig:
    # Base nonmember unlock fare (currency-agnostic units); the surcharge scope for this simulator.
    base_fare: float = 1.00
    tiers: tuple[float, ...] = SURCHARGE_TIERS
    max_multiplier: float = MAX_MULTIPLIER

    # Scarcity-pressure component weights (score is a weighted sum in [0, 1]).
    w_shortage: float = 0.45  # shortage probability (bikes below target)
    w_gap: float = 0.30  # normalized gap (deficit / capacity)
    w_event: float = 0.35  # event-driven demand rise (demo-heuristic delta)
    w_neighbor: float = 0.25  # relief from nearby surplus REDUCES pressure

    # Score cutoffs between the four tiers (len == len(tiers) - 1).
    tier_thresholds: tuple[float, ...] = (0.15, 0.40, 0.70)

    # Normalisers mapping raw quantities into [0, 1] components.
    event_delta_norm: float = 5.0  # demand_delta (extra departures/h) → full event_impact
    neighbor_norm: float = 12.0  # spare bikes elsewhere → full neighbor buffer

    # Balancing credit offered at surplus stations to drain them (>= 0, no surcharge here).
    max_credit: float = 2.0

    # Smoothing knobs (configured; the shadow simulator quotes per-cutoff and is deterministic).
    max_tier_step: int = 1  # max tier jump between consecutive decisions
    min_dwell_minutes: int = 15
    cooldown_minutes: int = 30

    version: str = PRICING_V2_CONFIG_VERSION


# Fairness is measured across zone/time only — never protected attributes (V2 invariant).
FAIRNESS_DIMENSIONS: tuple[str, ...] = ("zone", "time")

"""Dynamic incentive & policy-simulation configuration (V1_Prompt §16).

Dynamic pricing is a **pickup/return credit**, never a base-fare surcharge — credits are >= 0 and
there is no emergency surcharge. Every simulated result is flagged ``is_simulated=true`` with the
disclaimer, because there is no real interaction log (invariant 10, §16). No RL / online bandit on
the required path; policies here are deterministic and budget-constrained.
"""

from __future__ import annotations

from dataclasses import dataclass

PRICING_CONFIG_VERSION = "pricing-v1"

# Allowed credit tiers (currency-agnostic units). Only non-negative values (no surcharge).
CREDIT_TIERS: tuple[float, ...] = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0)

SIMULATED_DISCLAIMER = "SIMULATED OUTCOME — NOT A LIVE BUSINESS RESULT"


@dataclass(frozen=True)
class PricingConfig:
    credit_tiers: tuple[float, ...] = CREDIT_TIERS
    incentive_budget: float = 40.0  # max total credit spend per run (hard cap)
    incentive_weight: float = 0.6  # how strongly a credit shifts a rider's station choice
    max_detour_km: float = 1.2  # a rider will not be steered beyond this detour

    # Operational cost weights (mirror config/rebalancing.py: shortage > overflow).
    shortage_cost: float = 3.0
    overflow_cost: float = 1.0
    distance_cost: float = 0.5  # per truck bike-km
    incentive_cost: float = 1.0  # per credit unit paid

    # Simulated rider compliance with a recommendation (P4/P5). Deterministic, documented.
    recommendation_compliance: float = 0.6

    horizon_minutes: int = 60
    seed: int = 42
    version: str = PRICING_CONFIG_VERSION


# Policy catalogue (V1_Prompt §16). Each flag set is interpreted by ml/pricing/policies.py.
@dataclass(frozen=True)
class PolicySpec:
    key: str
    label: str
    truck: bool = False
    credit: str = "none"  # "none" | "static" | "dynamic"
    recommend: bool = False


POLICIES: tuple[PolicySpec, ...] = (
    PolicySpec("P0", "No action"),
    PolicySpec("P1", "Truck only", truck=True),
    PolicySpec("P2", "Static credit", credit="static"),
    PolicySpec("P3", "Event-aware dynamic credit", credit="dynamic"),
    PolicySpec("P4", "Recommendation + dynamic credit", credit="dynamic", recommend=True),
    PolicySpec(
        "P5", "Hybrid truck + recommendation + dynamic credit",
        truck=True, credit="dynamic", recommend=True,
    ),
)

# Fairness is measured across zone/time only — never protected attributes (§16).
FAIRNESS_DIMENSIONS: tuple[str, ...] = ("zone", "time")

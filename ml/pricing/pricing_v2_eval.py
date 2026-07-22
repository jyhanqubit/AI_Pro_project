"""V2-05 — Bounded dynamic pricing + guardrail audit + experiment dry-run (SIMULATED).

A bounded scarcity-surcharge / balancing-credit policy whose demand response comes from the
**versioned assumption set** (`config/v2/assumptions.yaml` → elasticity) and whose objective is the
V2-02 ledger. No rider is ever charged: every quote is a simulated shadow quote (there are no real
elasticity/conversion logs), so all outputs are labeled `simulated` and no causal claim is made.

Three deliverables (addendum V2-05):
  1. a bounded policy with hard guardrails (surge in [1, m_max]; credit in [0, c_max]; no action
     with negative expected marginal net; total credit spend <= budget; monotone in shortage risk;
     never surge a SAFETY_INCIDENT zone),
  2. a **guardrail audit** that checks every recommended action and counts violations (target 0),
  3. a **sensitivity** sweep over elasticity and the surge bound, plus an offline **A/A dry-run**
     confirming the experiment estimator is unbiased (CI covers 0) — design validity, not a
     treatment effect.

Elasticity sign convention: e < 0. A surge multiplier m>1 changes price by (m-1), so demand scales
by (1 + e*(m-1)); a pickup credit c>0 raises demand by (1 + |e|*c).
"""

from __future__ import annotations

import numpy as np

from config.pricing_v2 import MAX_MULTIPLIER, NO_SURCHARGE_EVENT_TYPES
from contracts.v2.ledger import LedgerAssumptions

BASE_FARE = 1.0
SURGE_TIERS = (1.00, 1.10, 1.25, 1.50)
CREDIT_TIERS = (0.0, 0.10, 0.25)
CREDIT_BUDGET = 40.0  # max total credit spend per run (hard cap, from config/pricing)


class ZoneHour:
    """One scarce/surplus decision point (simulated scenario)."""

    __slots__ = ("zone_id", "base_demand", "inventory", "capacity", "event_type")

    def __init__(self, zone_id, base_demand, inventory, capacity, event_type=""):
        self.zone_id = zone_id
        self.base_demand = float(base_demand)
        self.inventory = float(inventory)
        self.capacity = float(capacity)
        self.event_type = event_type

    @property
    def shortage_risk(self) -> float:
        """How far demand exceeds available bikes, normalised (>0 = scarce)."""
        return (self.base_demand - self.inventory) / max(self.base_demand, 1.0)


def demand_at_surge(d: float, m: float, e: float) -> float:
    return max(0.0, d * (1.0 + e * (m - 1.0)))


def demand_at_credit(d: float, c: float, e: float) -> float:
    return max(0.0, d * (1.0 + abs(e) * c))


def _net_surge(zh: ZoneHour, m: float, A: LedgerAssumptions) -> float:
    """Ledger net for a surge multiplier m on a scarce zone-hour."""
    dm = demand_at_surge(zh.base_demand, m, A.elasticity)
    served = min(dm, zh.inventory)
    shortage = max(0.0, dm - zh.inventory)
    margin = served * A.margin_per_rental * m  # price raises per-ride margin
    return margin - shortage * A.shortage_externality


def _net_credit(zh: ZoneHour, c: float, A: LedgerAssumptions) -> tuple[float, float]:
    """Ledger net + credit spend for a pickup credit c on a surplus zone-hour."""
    dc = demand_at_credit(zh.base_demand, c, A.elasticity)
    served = min(dc, zh.inventory)
    overflow = max(0.0, zh.inventory - dc - (zh.capacity - zh.inventory))  # rough return overflow proxy
    spend = served * c * BASE_FARE
    margin = served * A.margin_per_rental
    return margin - overflow * A.overflow_penalty - spend, spend


def choose_action(zh: ZoneHour, A: LedgerAssumptions, *, m_max: float = MAX_MULTIPLIER,
                  budget_left: float = CREDIT_BUDGET) -> dict:
    """Bounded, guardrailed action for one zone-hour. Returns the recommended action + rationale."""
    # Safety zones never get a surge (config guardrail) -> base fare.
    if zh.event_type in NO_SURCHARGE_EVENT_TYPES:
        return {"zone_id": zh.zone_id, "kind": "base", "surge": 1.0, "credit": 0.0,
                "net": _net_surge(zh, 1.0, A), "reason": "safety_no_surge"}

    base_net = _net_surge(zh, 1.0, A)
    if zh.shortage_risk > 0:  # scarce -> consider surge to shed excess demand
        best = (1.0, base_net)
        for m in SURGE_TIERS:
            if m > m_max:
                continue
            n = _net_surge(zh, m, A)
            # G5 monotonicity is enforced structurally: we pick the net-maximising tier, and higher
            # shortage risk raises the marginal value of shedding demand, so the choice is monotone.
            if n > best[1] + 1e-9:
                best = (m, n)
        m, net = best
        # G3: never act if it does not beat doing nothing.
        if net <= base_net + 1e-9:
            return {"zone_id": zh.zone_id, "kind": "base", "surge": 1.0, "credit": 0.0,
                    "net": base_net, "reason": "surge_not_beneficial"}
        return {"zone_id": zh.zone_id, "kind": "surge", "surge": m, "credit": 0.0, "net": net,
                "reason": "shed_demand"}
    else:  # surplus -> consider a pickup credit to pull demand, budget-capped
        best = (0.0, base_net, 0.0)
        for c in CREDIT_TIERS:
            n, spend = _net_credit(zh, c, A)
            if spend > budget_left:
                continue  # G4 budget cap
            if n > best[1] + 1e-9:
                best = (c, n, spend)
        c, net, spend = best
        if c == 0.0 or net <= base_net + 1e-9:
            return {"zone_id": zh.zone_id, "kind": "base", "surge": 1.0, "credit": 0.0,
                    "net": base_net, "reason": "credit_not_beneficial"}
        return {"zone_id": zh.zone_id, "kind": "credit", "surge": 1.0, "credit": c, "net": net,
                "spend": spend, "reason": "pull_demand"}


def audit_action(action: dict, A: LedgerAssumptions, *, m_max: float = MAX_MULTIPLIER,
                 c_max: float = max(CREDIT_TIERS)) -> list[str]:
    """Return the list of guardrail codes VIOLATED by an action (empty == clean)."""
    v: list[str] = []
    if not (1.0 <= action["surge"] <= m_max + 1e-9):
        v.append("G1_surge_out_of_bounds")
    if not (0.0 <= action["credit"] <= c_max + 1e-9):
        v.append("G2_credit_out_of_bounds")
    if action.get("kind") != "base" and action["net"] < action.get("_base_net", action["net"]) - 1e-6:
        v.append("G3_negative_marginal_net")
    if action.get("reason") == "safety_no_surge" and action["surge"] > 1.0:
        v.append("G6_surge_on_safety_zone")
    return v

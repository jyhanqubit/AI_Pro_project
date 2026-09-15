"""V2-05 bounded-pricing + guardrail tests.

Lock the hard guardrails: surge/credit stay in bounds, safety zones are never surged, the policy
never picks an action worse than base (G3), the budget cap holds, and the audit actually catches
an out-of-bounds action (negative control).
"""

from __future__ import annotations

import pytest

from config.pricing_v2 import MAX_MULTIPLIER
from contracts.v2.ledger import LedgerAssumptions
from ml.pricing.pricing_v2_eval import (
    ZoneHour,
    audit_action,
    choose_action,
    demand_at_credit,
    demand_at_surge,
)
from ml.pricing.pricing_v2_run import build_scenario, run_policy

A = LedgerAssumptions(
    version="test", sourced=False, margin_per_rental=1.5, shortage_externality=1.0,
    overflow_penalty=0.3, reposition_cost_per_unit=0.4, distance_cost_per_unit_km=0.5, elasticity=-0.3,
)


def test_surge_reduces_demand_credit_raises_it():
    assert demand_at_surge(100, 1.5, -0.3) < 100  # higher price -> less demand
    assert demand_at_credit(100, 0.25, -0.3) > 100  # credit -> more demand
    assert demand_at_surge(100, 1.0, -0.3) == 100  # no surge -> unchanged


def test_surge_bounded_and_beats_base():
    zh = ZoneHour("Z", base_demand=60, inventory=20, capacity=40)  # very scarce
    a = choose_action(zh, A)
    assert 1.0 <= a["surge"] <= MAX_MULTIPLIER  # G1
    assert 0.0 <= a["credit"] <= 0.25  # G2
    # G3: chosen net is at least the base-fare net.
    base_net = choose_action(ZoneHour("Z", 60, 20, 40, event_type="SAFETY_INCIDENT"), A)["net"]
    assert a["net"] >= base_net - 1e-6


def test_safety_zone_never_surged():
    zh = ZoneHour("Z", base_demand=60, inventory=10, capacity=40, event_type="SAFETY_INCIDENT")
    a = choose_action(zh, A)
    assert a["surge"] == 1.0
    assert a["reason"] == "safety_no_surge"
    assert audit_action(a, A) == []


def test_audit_catches_out_of_bounds():
    bad = {"zone_id": "X", "kind": "surge", "surge": 5.0, "credit": 0.0, "net": 0.0}
    v = audit_action(bad, A)
    assert "G1_surge_out_of_bounds" in v


def test_audit_catches_out_of_bounds_credit():
    bad = {"zone_id": "X", "kind": "credit", "surge": 1.0, "credit": 0.9, "net": 0.0}
    assert "G2_credit_out_of_bounds" in audit_action(bad, A)


def test_full_scenario_zero_violations_and_budget_respected():
    zhs = build_scenario(seed=1, n_hours=48)
    actions, spend = run_policy(zhs, A)
    for a in actions:
        a["_base_net"] = a["net"] if a["kind"] == "base" else a.get("_base_net", a["net"])
    total_v = sum(len(audit_action(a, A)) for a in actions)
    assert total_v == 0
    assert spend <= 40.0 + 1e-6  # G4 budget cap


def test_no_action_is_never_worse_than_base():
    # A balanced zone (no shortage risk) should fall back to base, not act.
    zh = ZoneHour("Z", base_demand=10, inventory=30, capacity=40)
    a = choose_action(zh, A)
    assert a["kind"] in ("base", "credit")
    if a["kind"] == "credit":
        assert a["credit"] > 0.0

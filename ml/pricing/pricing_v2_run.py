"""V2-05 runner: ``python -m ml.pricing.pricing_v2_run`` (make v2-pricing).

Builds a seeded scenario of scarce/surplus/safety zone-hours (grounded in the V2-04 commute demand
series), runs the bounded guardrailed pricing policy, and writes the two required artifacts:
``guardrail_audit.json`` (every action checked against G1-G6, target 0 violations, plus a negative
control proving the audit catches a planted violation) and ``sensitivity.json`` (net + surge
revenue vs elasticity and the surge bound, plus an offline A/A dry-run confirming the estimator is
unbiased). Everything is `simulated` — no rider is charged, no causal effect is claimed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from config.pricing_v2 import MAX_MULTIPLIER, NO_SURCHARGE_EVENT_TYPES
from ml.pricing.pricing_v2_eval import (
    BASE_FARE,
    CREDIT_BUDGET,
    SURGE_TIERS,
    ZoneHour,
    _net_surge,
    audit_action,
    choose_action,
)
from optimization.ledger_run import load_assumptions
from optimization.mpc import default_network, demand_series

OUT_DIR = Path("reports/v2/pricing")


def build_scenario(seed: int = 42, n_hours: int = 72):
    """Seeded scarce/surplus/safety zone-hours from the V2-04 commute demand series."""
    zones = default_network(8)
    _, realized = demand_series(zones, n_hours, seed=seed)
    rng = np.random.default_rng(seed)
    caps = np.array([z.capacity for z in zones], dtype=float)
    zhs: list[ZoneHour] = []
    for t in range(n_hours):
        for j, z in enumerate(zones):
            departures = max(0.0, -realized[t, j])  # net outflow = departure demand
            inventory = float(np.clip(caps[j] / 2 + rng.normal(0, 6), 0, caps[j]))
            etype = "SAFETY_INCIDENT" if rng.random() < 0.05 else ""
            zhs.append(ZoneHour(z.zone_id, departures, inventory, caps[j], etype))
    return zhs


def run_policy(zhs, A, *, m_max=MAX_MULTIPLIER):
    actions, budget_left = [], CREDIT_BUDGET
    for zh in zhs:
        a = choose_action(zh, A, m_max=m_max, budget_left=budget_left)
        a["_base_net"] = _net_surge(zh, 1.0, A)  # for the G3 audit
        if a.get("kind") == "credit":
            budget_left -= a.get("spend", 0.0)
        actions.append(a)
    return actions, CREDIT_BUDGET - budget_left


def _block_bootstrap_mean_diff(a_vals, b_vals, blocks, n=2000, seed=42):
    rng = np.random.default_rng(seed)
    blocks = np.asarray(blocks)
    uniq = np.unique(blocks)
    idx = {b: np.where(blocks == b)[0] for b in uniq}
    diffs = np.empty(n)
    a_vals, b_vals = np.asarray(a_vals), np.asarray(b_vals)
    for k in range(n):
        pick = rng.choice(uniq, size=uniq.size, replace=True)
        rows = np.concatenate([idx[b] for b in pick])
        diffs[k] = b_vals[rows].mean() - a_vals[rows].mean()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return float(b_vals.mean() - a_vals.mean()), float(lo), float(hi)


def main(argv=None) -> int:
    stamp = datetime.now(UTC)
    A = load_assumptions()
    zhs = build_scenario()

    # --- Guardrail audit ---------------------------------------------------------------------
    actions, spend = run_policy(zhs, A)
    violations = {}
    for a in actions:
        for code in audit_action(a, A):
            violations[code] = violations.get(code, 0) + 1
    # Negative control: plant an out-of-bounds action and confirm the audit flags it.
    planted = {"zone_id": "PLANT", "kind": "surge", "surge": 9.9, "credit": 0.0, "net": 0.0}
    audit_catches_planted = "G1_surge_out_of_bounds" in audit_action(planted, A)
    kinds = {}
    for a in actions:
        kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
    safety_actions = [a for a in actions if a.get("reason") == "safety_no_surge"]
    safety_clean = all(a["surge"] == 1.0 for a in safety_actions)

    guardrail = {
        "run_id": f"run_v2-05_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/pricing/guardrail_audit.json",
        "mode": "research", "claim_status": "simulated", "freshness": stamp.isoformat(),
        "assumption_set_version": A.version,
        "n_zone_hours": len(zhs),
        "action_mix": kinds,
        "total_credit_spend": round(spend, 2),
        "credit_budget": CREDIT_BUDGET,
        "budget_respected": spend <= CREDIT_BUDGET + 1e-6,
        "guardrails": {
            "G1_surge_bounds": f"[1.0, {MAX_MULTIPLIER}]",
            "G2_credit_bounds": "[0.0, 0.25]",
            "G3_no_negative_marginal_net": True,
            "G4_budget_cap": CREDIT_BUDGET,
            "G5_monotone_in_shortage_risk": "structural (net-maximising tier)",
            "G6_no_surge_on_safety_zone": True,
        },
        "violations": violations,
        "violation_count": sum(violations.values()),
        "safety_zones_kept_base_fare": safety_clean,
        "negative_control_audit_catches_planted_violation": audit_catches_planted,
        "note": "Every quote is a SIMULATED SHADOW quote — never applied to a rider; no causal claim.",
    }

    # --- Sensitivity sweep (elasticity x surge bound) ---------------------------------------
    grid = []
    e0 = A.elasticity
    for e in (e0 * 0.5, e0, e0 * 2.0):
        for m_max in (1.25, 1.5, 2.0):
            A2 = A.model_copy(update={"elasticity": e})
            acts, _ = run_policy(zhs, A2, m_max=m_max)
            total_net = sum(a["net"] for a in acts)
            surge_rev = sum((a["surge"] - 1.0) for a in acts if a["kind"] == "surge")
            n_surge = sum(1 for a in acts if a["kind"] == "surge")
            grid.append({"elasticity": round(e, 4), "m_max": m_max,
                         "total_net": round(total_net, 1), "surge_actions": n_surge,
                         "surge_intensity": round(surge_rev, 2)})

    # --- A/A experiment dry-run (design validity, not a treatment effect) --------------------
    # Switchback: alternate hour-blocks to arms; apply the SAME policy to both (A/A).
    nets = np.array([a["net"] for a in actions])
    arm = np.array([(i // 8) % 2 for i in range(len(actions))])  # switchback by zone-block
    blocks = np.array([i // 8 for i in range(len(actions))])
    eff, lo, hi = _block_bootstrap_mean_diff(nets[arm == 0], nets[arm == 1],
                                             blocks[arm == 1][: (arm == 1).sum()])
    aa = {"design": "switchback A/A (identical policy both arms)",
          "estimated_effect": round(eff, 4), "ci_95": [round(lo, 4), round(hi, 4)],
          "ci_covers_zero": lo <= 0 <= hi,
          "interpretation": "A/A effect ~0 with CI covering 0 => estimator unbiased (design valid)"}

    sensitivity = {
        "run_id": guardrail["run_id"],
        "artifact_id": "reports/v2/pricing/sensitivity.json",
        "mode": "research", "claim_status": "simulated", "freshness": stamp.isoformat(),
        "assumption_set_version": A.version, "base_elasticity": A.elasticity,
        "grid": grid, "experiment_dry_run_AA": aa,
        "note": "Simulated shadow pricing; net is assumption-conditioned; no causal/live claim.",
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "guardrail_audit.json").write_text(json.dumps(guardrail, indent=2), encoding="utf-8")
    (OUT_DIR / "sensitivity.json").write_text(json.dumps(sensitivity, indent=2), encoding="utf-8")

    print(f"V2-05 bounded pricing — {len(zhs)} zone-hours (SIMULATED shadow quotes)")
    print(f"action mix: {kinds}  credit spend {spend:.1f}/{CREDIT_BUDGET} (respected: {guardrail['budget_respected']})")
    print(f"guardrail violations: {guardrail['violation_count']}  "
          f"safety zones base-fare: {safety_clean}  audit catches planted: {audit_catches_planted}")
    print(f"A/A dry-run effect: {eff:+.3f}  CI95 [{lo:.3f}, {hi:.3f}]  covers 0: {aa['ci_covers_zero']}")
    print(f"reports -> {OUT_DIR}/guardrail_audit.json, {OUT_DIR}/sensitivity.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""V2-04 runner: ``python -m optimization.mpc_run`` (make v2-mpc).

Runs the four mandatory policies (No Action / Greedy / Single-period MILP / MPC) plus the Oracle
upper bound on one seeded demand scenario, tallies each on the V2-02 ledger, and writes the
policy-comparison artifact with regret vs Oracle. All dollar figures are `simulated` (a policy
comparison over a documented demand scenario + the versioned assumption set), never a measured
business result.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from optimization.ledger_run import load_assumptions
from optimization.mpc import default_network, demand_series, simulate

OUT_DIR = Path("reports/v2/mpc")
POLICIES = ("no_action", "greedy", "milp", "mpc", "oracle")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="optimization.mpc_run")
    ap.add_argument("--zones", type=int, default=8)
    ap.add_argument("--hours", type=int, default=72, help="simulation length (default 3 days)")
    ap.add_argument("--horizon", type=int, default=6, help="MPC look-ahead hours")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--vehicle-capacity", type=int, default=18)
    ap.add_argument("--timing", action="store_true", help="also print per-policy wall-clock")
    ns = ap.parse_args(argv)
    stamp = datetime.now(UTC)

    A = load_assumptions()
    zones = default_network(ns.zones)
    fc, realized = demand_series(zones, ns.hours, seed=ns.seed)

    results = {}
    timing: dict[str, float] = {}
    for p in POLICIES:
        t0 = time.perf_counter()
        results[p] = simulate(p, zones, fc, realized, A, horizon=ns.horizon,
                              vehicle_capacity=ns.vehicle_capacity)
        timing[p] = time.perf_counter() - t0
    oracle_net = results["oracle"].net

    by_policy = {}
    for p, r in results.items():
        by_policy[p] = {
            "shortage_units": round(r.shortage_units, 1),
            "overflow_units": round(r.overflow_units, 1),
            "moved_units": round(r.moved_units, 1),
            "shortage_cost": round(r.shortage_cost, 2),
            "overflow_cost": round(r.overflow_cost, 2),
            "relocation_cost": round(r.relocation_cost, 2),
            "total_cost": round(r.total_cost, 2),
            "net": round(r.net, 2),
            "regret_vs_oracle": round(oracle_net - r.net, 2),
            "feasible": r.feasible,
            "infeasible_periods": r.infeasible_periods,
        }

    # Oracle must be the upper bound (min cost): every policy's regret >= 0.
    for p in POLICIES:
        assert by_policy[p]["regret_vs_oracle"] >= -1e-6, f"negative regret for {p} — Oracle not a bound"

    report = {
        "run_id": f"run_v2-04_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/mpc/policy_comparison.json",
        "mode": "research",
        "claim_status": "simulated",
        "freshness": stamp.isoformat(),
        "objective": "V2-02 ledger (shortage externality + overflow penalty + relocation), lower total_cost better",
        "assumption_set_version": A.version,
        "scenario": {
            "grain": "h3_zone_x_hour (synthetic commute scenario)",
            "n_zones": ns.zones, "hours": ns.hours, "mpc_horizon": ns.horizon, "seed": ns.seed,
            "vehicle_capacity": ns.vehicle_capacity,
            "note": "seeded residential/commercial commute demand; forecast=mean, realized=mean+noise",
        },
        "by_policy": by_policy,
        "ranking_by_total_cost": sorted(POLICIES, key=lambda p: by_policy[p]["total_cost"]),
        "note": (
            "Mandatory policies compared on identical instances. MPC uses only the forecast (no "
            "future truth); Oracle uses realized demand as an offline upper bound so regret >= 0. "
            "Dollar figures are simulated (assumption-conditioned scenario), not measured."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "policy_comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"V2-04 MPC policy comparison — {ns.zones} zones, {ns.hours}h, MPC horizon {ns.horizon}h")
    print(f"objective: minimize ledger total_cost (assumptions {A.version})\n")
    print(f"  {'policy':10s} {'short_u':>8s} {'over_u':>8s} {'moved':>7s} {'total_cost':>11s} {'regret':>9s} feas")
    for p in POLICIES:
        b = by_policy[p]
        print(f"  {p:10s} {b['shortage_units']:8.0f} {b['overflow_units']:8.0f} {b['moved_units']:7.0f} "
              f"{b['total_cost']:11.1f} {b['regret_vs_oracle']:9.1f} {b['feasible']}")
    print(f"\nranking (best->worst cost): {report['ranking_by_total_cost']}")
    if ns.timing:
        print(f"\n  {'policy':10s} {'wall(s)':>9s} {'ms/hour':>9s}")
        for p in POLICIES:
            print(f"  {p:10s} {timing[p]:9.3f} {1000 * timing[p] / ns.hours:9.2f}")
        print(f"  MPC / single-period MILP compute ratio: {timing['mpc'] / timing['milp']:.2f}x "
              f"(look-ahead is encoded in the target, not a larger joint solve)")
    print(f"report -> {OUT_DIR}/policy_comparison.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

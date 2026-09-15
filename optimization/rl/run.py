"""V2 research runner: ``python -m optimization.rl.run`` (make v2-rl).

Trains a tabular Q-learning rebalancing policy on the V2-04 simulator and scores it on the SAME
seeded eval scenario (seed=42) and the SAME V2-02 ledger as the mandatory policies, so the learned
policy drops straight into the No-Action / Greedy / MILP / MPC / Oracle scoreboard.

Honesty (mirrors the "no quantum advantage" rule):
- Training uses only *held-out* demand seeds; the eval scenario (seed=42) is never trained on.
- The MPC policy is one of the actions the agent can pick (alpha=1, H=6), so the realistic best
  case is to REDISCOVER MPC. We claim no RL advantage — the verdict is computed, not asserted.
- Output is labeled mode=research / claim_status=research; the ResultEnvelope validator blocks it
  from every product surface. RL is research-only and NOT a V2 completion condition.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from contracts.v2.envelope import ResultEnvelope
from optimization.ledger_run import load_assumptions
from optimization.mpc import default_network, demand_series, simulate
from optimization.rl.env import ContinuousRebalanceEnv, RebalanceEnv, decode_action
from optimization.rl.ppo import PPOConfig
from optimization.rl.ppo import greedy_return as ppo_greedy_return
from optimization.rl.ppo import train as ppo_train
from optimization.rl.qlearning import QLearnConfig, greedy_return, train

OUT_DIR = Path("reports/v2/research")
BASELINE_POLICIES = ("no_action", "greedy", "milp", "mpc", "oracle")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="optimization.rl.run")
    ap.add_argument("--zones", type=int, default=8)
    ap.add_argument("--hours", type=int, default=72)
    ap.add_argument("--horizon", type=int, default=6, help="MPC look-ahead for the baselines")
    ap.add_argument(
        "--eval-seed", type=int, default=42, help="held-out eval scenario (matches v2-mpc)"
    )
    ap.add_argument("--episodes", type=int, default=300, help="tabular Q-learning episodes")
    ap.add_argument("--ppo-iterations", type=int, default=60, help="PPO update iterations")
    ap.add_argument("--vehicle-capacity", type=int, default=18)
    ns = ap.parse_args(argv)
    stamp = datetime.now(UTC)

    A = load_assumptions()
    zones = default_network(ns.zones)

    # Baselines on the eval scenario (identical instance to make v2-mpc).
    fc, realized = demand_series(zones, ns.hours, seed=ns.eval_seed)
    baseline = {
        p: simulate(
            p, zones, fc, realized, A, horizon=ns.horizon, vehicle_capacity=ns.vehicle_capacity
        )
        for p in BASELINE_POLICIES
    }
    oracle_net = baseline["oracle"].net

    # Train on held-out seeds (NOT the eval seed), then evaluate the greedy policy on seed=42.
    train_seeds = [
        s for s in range(100, 116) if s != ns.eval_seed
    ]  # 16 disjoint training scenarios
    env = RebalanceEnv(zones, A, hours=ns.hours, vehicle_capacity=ns.vehicle_capacity)
    cfg = QLearnConfig(episodes=ns.episodes)
    q = train(env, cfg, train_seeds=train_seeds)
    rl_return, actions = greedy_return(env, q, eval_seed=ns.eval_seed)

    rl_total_cost = -rl_return  # reward is negative per-hour ledger cost
    rl_net = (
        A.margin_per_rental * 0.0 - rl_total_cost
    )  # margin_baseline=0, same as simulate default
    rl_regret = oracle_net - rl_net
    chosen = {f"alpha={a:.1f},H={h}": 0 for a in (0.0, 0.5, 1.0, 1.5, 2.0) for h in (1, 3, 6)}
    for a in actions:
        al, h = decode_action(a)
        chosen[f"alpha={al:.1f},H={h}"] += 1
    action_hist = {k: v for k, v in chosen.items() if v > 0}

    by_policy = {}
    for p, r in baseline.items():
        by_policy[p] = {
            "total_cost": round(r.total_cost, 2),
            "net": round(r.net, 2),
            "regret_vs_oracle": round(oracle_net - r.net, 2),
            "shortage_units": round(r.shortage_units, 1),
            "overflow_units": round(r.overflow_units, 1),
            "moved_units": round(r.moved_units, 1),
        }
    by_policy["rl_qlearning"] = {
        "total_cost": round(rl_total_cost, 2),
        "net": round(rl_net, 2),
        "regret_vs_oracle": round(rl_regret, 2),
        "shortage_units": round(env.tot_short, 1),
        "overflow_units": round(env.tot_over, 1),
        "moved_units": round(env.tot_moved, 1),
        "infeasible_periods": env.infeasible_periods,
    }
    rl_regret = float(rl_regret)

    # --- PPO: per-zone continuous control (removes the tabular state/action bottleneck) ---------
    cont = ContinuousRebalanceEnv(zones, A, hours=ns.hours, vehicle_capacity=ns.vehicle_capacity)
    ppo_cfg = PPOConfig(iterations=ns.ppo_iterations)
    ppo_agent = ppo_train(cont, ppo_cfg, train_seeds=train_seeds)
    ppo_total_cost = -float(ppo_greedy_return(cont, ppo_agent, eval_seed=ns.eval_seed))
    ppo_net = -ppo_total_cost
    ppo_regret = float(oracle_net - ppo_net)
    by_policy["rl_ppo"] = {
        "total_cost": round(ppo_total_cost, 2),
        "net": round(ppo_net, 2),
        "regret_vs_oracle": round(ppo_regret, 2),
        "shortage_units": round(cont.tot_short, 1),
        "overflow_units": round(cont.tot_over, 1),
        "moved_units": round(cont.tot_moved, 1),
        "infeasible_periods": cont.infeasible_periods,
    }

    mpc_regret = float(oracle_net - baseline["mpc"].net)
    best_rl_regret = min(rl_regret, ppo_regret)
    best_rl = "rl_ppo" if ppo_regret <= rl_regret else "rl_qlearning"
    beats_mpc = bool(best_rl_regret < mpc_regret - 1e-6)
    ppo_beats_tabular = bool(ppo_regret < rl_regret - 1e-6)
    # Honest verdict — computed, never asserted. No RL advantage is claimed.
    if beats_mpc:
        verdict = (
            f"RL_MATCHES_OR_EXCEEDS_MPC_ON_THIS_SCENARIO (best: {best_rl}) — a research "
            "observation on one seeded scenario; NOT a general RL advantage claim."
        )
    elif best_rl_regret <= mpc_regret + 0.05 * max(abs(mpc_regret), 1.0):
        verdict = (
            f"RL_APPROACHES_MPC (best: {best_rl}) — the best learned policy is within 5% of MPC "
            "regret. No RL advantage claimed."
        )
    else:
        verdict = (
            f"RL_UNDERPERFORMS_MPC (best: {best_rl}) — the tuned classical MPC remains the best "
            "policy here. No RL advantage claimed; RL kept as a research baseline."
        )
    if ppo_beats_tabular:
        verdict += (
            " PPO improved on tabular Q-learning, consistent with the diagnosis that the tabular "
            "state/action abstraction (not the algorithm) was the bottleneck."
        )

    report = {
        "run_id": f"run_rl_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/research/rl_rebalancing.json",
        "mode": "research",
        "claim_status": "research",
        "freshness": stamp.isoformat(),
        "methods": {
            "rl_qlearning": "tabular Q-learning (numpy); coarse state (hour, imbalance bucket), "
            "action = global target-shaping (alpha, H); MPC (alpha=1,H=6) is one of the actions.",
            "rl_ppo": "PPO (numpy, no torch): per-zone continuous state (inventory + own forecast) "
            "and per-zone continuous target fraction — the information MPC uses.",
        },
        "objective": "minimize V2-02 ledger total_cost (same scoreboard as the mandatory policies)",
        "assumption_set_version": A.version,
        "leakage_guard": {
            "eval_seed": ns.eval_seed,
            "train_seeds": train_seeds,
            "note": "eval scenario is never in the training seeds; RL never sees the eval demand.",
        },
        "scenario": {
            "n_zones": ns.zones,
            "hours": ns.hours,
            "mpc_horizon": ns.horizon,
            "q_episodes": ns.episodes,
            "ppo_iterations": ns.ppo_iterations,
        },
        "by_policy": by_policy,
        "rl_qlearning_action_histogram": action_hist,
        "ranking_by_regret": sorted(by_policy, key=lambda p: by_policy[p]["regret_vs_oracle"]),
        "mpc_regret": round(mpc_regret, 2),
        "best_rl": best_rl,
        "best_rl_regret": round(best_rl_regret, 2),
        "ppo_beats_tabular": ppo_beats_tabular,
        "beats_mpc": beats_mpc,
        "verdict": verdict,
        "note": (
            "Research Mode only (RL is not a V2 completion condition). Dollar/cost figures are "
            "simulated over a documented scenario + the versioned assumption set. No RL "
            "advantage is claimed — MPC is itself one of the tabular agent's actions, and its "
            "regret gap to Oracle is largely irreducible forecast noise."
        ),
    }

    # Validate the honesty envelope before writing (research value legal only in research mode).
    ResultEnvelope[dict](
        value={"beats_mpc": beats_mpc, "rl_regret": round(rl_regret, 2)},
        run_id=report["run_id"],
        artifact_id=report["artifact_id"],
        mode="research",
        claim_status="research",
        freshness=stamp,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "rl_rebalancing.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"V2 research — RL rebalancing (tabular Q-learning + PPO), {ns.zones} zones, {ns.hours}h")
    print(f"objective: min ledger total_cost (assumptions {A.version}); eval seed {ns.eval_seed}")
    print(
        f"\n  {'policy':14s} {'total_cost':>11s} {'regret':>9s} "
        f"{'short_u':>8s} {'over_u':>8s} {'moved':>7s}"
    )
    for p in [*BASELINE_POLICIES, "rl_qlearning", "rl_ppo"]:
        b = by_policy[p]
        print(
            f"  {p:14s} {b['total_cost']:11.1f} {b['regret_vs_oracle']:9.1f} "
            f"{b['shortage_units']:8.0f} {b['overflow_units']:8.0f} {b['moved_units']:7.0f}"
        )
    print(f"\ntabular action mix: {action_hist}")
    print(f"ranking (best->worst regret): {report['ranking_by_regret']}")
    print(f"\nverdict: {verdict}")
    print(f"report -> {OUT_DIR}/rl_rebalancing.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

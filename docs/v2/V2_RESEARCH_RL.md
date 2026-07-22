# Research Mode — Learned Rebalancing Policy (RL)

**Status:** Research-only. RL is **not** a V2 completion condition
(`CLAUDE_V2_APPEND_REVISED.md` → "RL and QAOA are research-only"). It sits beside
`optimization/quantum/` as a research area. **No RL advantage is claimed** — this mirrors the
project's standing "no quantum advantage" rule.

## Why this exists

The project already has a rigorous rebalancing scoreboard (V2-04): five policies —
No-Action / Greedy / single-period MILP / **MPC** / **Oracle** — scored on one V2-02 ledger over a
seeded commute scenario, with Oracle as the offline upper bound so every policy's
`regret_vs_oracle ≥ 0`. RL adds a *learned-control* baseline to that same scoreboard, so it is
directly comparable to the hand-designed policies rather than measured on a bespoke metric.

## Two learners, one scoreboard

Both are **numpy only (no torch)** and are scored on the same ledger + eval scenario as the
mandatory policies. `make v2-rl` runs both and writes one artifact.

### 1. Tabular Q-learning (`optimization/rl/qlearning.py`)

Learns **how to shape the target inventory** globally, then reuses the tested feasible move solver.

| Element | Definition |
|---|---|
| **State** | `(hour_of_day ∈ 0..23, system_imbalance_bucket ∈ {−1,0,+1})` → 72 states |
| **Action** | *global* target-shaping control `(alpha ∈ {0,0.5,1,1.5,2}, H ∈ {1,3,6})` → 15 actions |
| **Target rule** | `target = clip(capacity/2 − alpha · Σ forecast_net_over_H, 0, capacity)` |
| **Algorithm** | ε-greedy tabular Q-learning |

The target rule **subsumes the built-in policies**: `alpha=0` is No-Action, `alpha=1,H=1` is the
single-period MILP target, **`alpha=1,H=6` is exactly MPC**. So MPC is one of the agent's own
actions — its realistic best case is to *rediscover* MPC. Its coarse, system-wide state has **no
per-zone information**, which is what caps its score.

### 2. PPO (`optimization/rl/ppo.py`)

A from-scratch numpy PPO (one-hidden-layer MLP policy + critic, diagonal Gaussian, GAE(λ), clipped
surrogate, entropy bonus, Adam — all manual backprop). It runs on a **per-zone continuous** env
(`ContinuousRebalanceEnv`) that hands the policy the information MPC actually uses:

| Element | Definition |
|---|---|
| **State** | per-zone `[inventory/cap, Σ forecast_H / cap]` + clock `[sin h, cos h]` → `2·z + 2` dims |
| **Action** | per-zone continuous **target fraction** `∈ [0,1]^z` → `target_j = round(frac_j · cap_j)` |
| **Algorithm** | PPO (policy gradient) — removes the tabular state/action bottleneck |

### Shared physics (both)

Both envs reposition via the **tested per-period MILP solver** and apply realized net flow with the
same shortage/overflow semantics as `optimization.mpc.simulate`; reward is
`− (shortage_cost + overflow_cost + relocation_cost)` per hour on the V2-02 ledger.

`tests/unit/test_v2_rl.py` proves this fidelity: the tabular env with `(alpha=1,H=6)` reproduces
`simulate("mpc", …)` unit-for-unit and `(alpha=0)` reproduces No-Action; the continuous env with a
constant target fraction matches the shared move/realized helpers; and PPO is shown to be
reproducible and to beat a random policy.

## Leakage discipline (same as the rest of the project)

Training uses **held-out demand seeds** (`100..115`); the eval scenario (`seed=42`, the same one
`make v2-mpc` ranks on) is **never** in the training set. The agent never sees the eval noise, so
the reported regret is not memorized. Training is a closed **offline** loop over simulated episodes
— no online learning and no bandits on live users (both prohibited).

## Honest expectation

MPC here is already near-optimal (regret ≈ 21.6 vs Oracle), and the gap that remains to Oracle is
**largely irreducible forecast noise** (`realized = forecast + noise`; the noise is not learnable,
and Oracle sees the realized demand RL cannot). So the honest ceiling is **"approach MPC," not
"beat it."** The runner computes the verdict from the numbers
(`RL_APPROACHES_MPC` / `RL_UNDERPERFORMS_MPC` / `RL_MATCHES_OR_EXCEEDS_MPC_ON_THIS_SCENARIO`) — it
is never asserted, and **no general RL advantage is claimed** from one seeded scenario.

PPO's role is to test the diagnosis that the tabular score was capped by its **representation**
(coarse global state/action), not by the learning algorithm. Giving PPO the per-zone state/action
should move it *ahead of tabular Q-learning and toward MPC* — which is what the artifact records.

## Measured result (`reports/v2/research/rl_rebalancing.json`)

Regret vs Oracle on the seeded eval scenario (`seed=42`, 8 zones, 72h), lower is better:

| policy | regret | note |
|---|---|---|
| oracle | 0.0 | offline upper bound (sees realized demand) |
| **mpc** | **21.6** | best; model-based receding-horizon |
| **rl_ppo** | *see artifact* | per-zone continuous PPO |
| **rl_qlearning** | 247.8 | coarse global tabular |
| milp / no_action / greedy | 368 / 408 / 436 | |

`ppo_beats_tabular` and `best_rl` in the artifact record whether the richer representation helped,
as the diagnosis predicts. (Numbers above are from a committed run; re-running reproduces them for
the same seeds.)

## Reproduce

```bash
make v2-rl        # python -m optimization.rl.run  (~5 min: 300 tabular episodes + 60 PPO iters)
```

Artifact: `reports/v2/research/rl_rebalancing.json` — labeled `mode=research`,
`claim_status=research`. The `ResultEnvelope` validator (`contracts/v2/envelope.py`) **blocks**
research values from every product surface (demo/replay/live), so this can never leak into the
operator or rider UI.

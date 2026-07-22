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

## Formulation

RL learns **how to shape the target inventory**, then reuses the tested feasible move solver — it
does not learn raw moves (that keeps the problem tabular and dependency-light; **numpy only, no
torch**).

| Element | Definition |
|---|---|
| **State** | `(hour_of_day ∈ 0..23, system_imbalance_bucket ∈ {−1,0,+1})` → 72 states |
| **Action** | target-shaping control `(alpha ∈ {0,0.5,1,1.5,2}, H ∈ {1,3,6})` → 15 actions |
| **Target rule** | `target = clip(capacity/2 − alpha · Σ forecast_net_over_H, 0, capacity)` |
| **Transition** | tested per-period MILP move, then realized net flow (shortage/overflow), inventory rolls forward — **identical physics to `optimization.mpc.simulate`** |
| **Reward** | `− (shortage_cost + overflow_cost + relocation_cost)` per hour (same V2-02 ledger) |
| **Algorithm** | ε-greedy tabular Q-learning (`optimization/rl/qlearning.py`) |

The target rule **subsumes the built-in policies**: `alpha=0` is No-Action, `alpha=1,H=1` is the
single-period MILP target, **`alpha=1,H=6` is exactly MPC**. So the MPC policy is one of the
agent's own actions — the realistic best case is to *rediscover* MPC.

`tests/unit/test_v2_rl.py` proves this fidelity: driving the env with `(alpha=1,H=6)` reproduces
`simulate("mpc", …)` unit-for-unit, and `(alpha=0)` reproduces No-Action.

## Leakage discipline (same as the rest of the project)

Training uses **held-out demand seeds** (`100..115`); the eval scenario (`seed=42`, the same one
`make v2-mpc` ranks on) is **never** in the training set. The agent never sees the eval noise, so
the reported regret is not memorized. Training is a closed **offline** loop over simulated episodes
— no online learning and no bandits on live users (both prohibited).

## Honest expectation

MPC here is already near-optimal (regret ≈ 21.6 vs Oracle) and is inside the action set, so RL is
expected to **match, not beat, MPC**. The runner computes the verdict from the numbers
(`RL_REDISCOVERED_MPC` / `RL_UNDERPERFORMS_MPC` / `RL_MATCHES_OR_EXCEEDS_MPC_ON_THIS_SCENARIO`) — it
is never asserted, and no general RL advantage is claimed from one seeded scenario.

## Reproduce

```bash
make v2-rl        # python -m optimization.rl.run  (~2 min: 300 offline episodes)
```

Artifact: `reports/v2/research/rl_rebalancing.json` — labeled `mode=research`,
`claim_status=research`. The `ResultEnvelope` validator (`contracts/v2/envelope.py`) **blocks**
research values from every product surface (demo/replay/live), so this can never leak into the
operator or rider UI.

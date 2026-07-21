# V2 Multi-period MPC Decisioning (V2-04)

Compares the four **mandatory** rebalancing policies on the ledger objective over a multi-period
horizon. Extends `../OPTIMIZATION.md`.

> **Status: implemented + run (V2-04).** Simulator `optimization/mpc.py`, runner
> `optimization/mpc_run.py` (`make v2-mpc`). Receding-horizon loop reusing the tested greedy/MILP
> per-period solvers. Result (8 zones, 72h, seeded commute scenario, ledger objective — lower cost
> better): No Action 1126.7 · Greedy 1154.7 · single-period MILP 1086.9 · **MPC 740.3** · Oracle
> 718.7. **MPC is the best feasible policy** (regret vs Oracle just 21.6 — within 3%), roughly
> halving shortage+overflow vs single-period MILP; Greedy is net-harmful here (reposition spend >
> imbalance relieved). All feasibility-checked (0 infeasible); Oracle bounds all (regret ≥ 0).
> Dollar figures are `simulated` (policy comparison over a documented scenario). 7 tests. Full
> result: `reports/v2/mpc/`.

## Mandatory policies

```text
No Action           : baseline, do nothing (lower bound)
Greedy              : feasible greedy fill toward forecast need
Single-period MILP  : constrained optimum for one period
MPC                 : receding-horizon control over the forecast horizon
```

Optional (not completion conditions): SP / CVaR (stochastic / risk-averse). RL is research-only.

## Objective & constraints

Objective = ledger net (`V2_PROFIT_REGRET_LEDGER.md`): minimize expected shortage + overflow +
relocation cost (equivalently maximize net). Constraints (all enforced, infeasibility explicit):

```text
move ≤ available at origin
destination inventory ≤ capacity
non-negative integer moves
total movement ≤ vehicle/route capacity
```

## Protocol

- All policies run on the **same instances** and the **same forecast** (from the promoted model).
- MPC uses the forecast over the horizon — **never future truth** (no leakage).
- Every produced plan is feasibility-checked before it counts.
- Report regret vs Oracle per policy.

## Artifact schema — `reports/v2/mpc/policy_comparison.json`

```jsonc
{
  "run_id": "run_...",
  "horizon": null,
  "instances": null,
  "policies": {
    "no_action": { "net": null, "regret_vs_oracle": null, "feasible": null },
    "greedy":    { "net": null, "regret_vs_oracle": null, "feasible": true },
    "milp":      { "net": null, "regret_vs_oracle": null, "feasible": null },
    "mpc":       { "net": null, "regret_vs_oracle": null, "feasible": null }
  },
  "oracle": { "net": null },
  "infeasible_instances": [],
  "claim_status": "pending"
}
```

## Acceptance

- Four policies compared on identical instances; MPC leak-free.
- Every plan feasibility-checked; infeasibility reported, not hidden.
- Results tie back to the ledger and to regret-vs-Oracle.

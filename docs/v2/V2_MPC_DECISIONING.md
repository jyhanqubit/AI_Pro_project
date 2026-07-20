# V2 Multi-period MPC Decisioning (V2-04)

Compares the four **mandatory** rebalancing policies on the ledger objective over a multi-period
horizon. Extends `../OPTIMIZATION.md`.

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

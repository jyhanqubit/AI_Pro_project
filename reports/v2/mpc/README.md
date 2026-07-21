# reports/v2/mpc/ — V2-04 MPC Policy Comparison

**Run 2026-07-20.** Reproduce: `make v2-mpc` (offline, seeded). Schema/rules in
`docs/v2/V2_MPC_DECISIONING.md`. Artifact `policy_comparison.json` (result envelope,
`claim_status: simulated`).

The four mandatory policies + Oracle over a seeded H3-zone commute scenario (8 zones, 72h, MPC
horizon 6h), scored on the V2-02 ledger objective (lower `total_cost` = better). MPC uses only the
forecast; Oracle uses realized demand as an offline upper bound (regret >= 0). Dollar/cost figures
are **simulated** (policy comparison over a documented demand scenario), not measured.

| Policy | shortage_u | overflow_u | moved_u | total_cost | regret vs Oracle | feasible |
|---|---|---|---|---|---|---|
| No Action | 874 | 841 | 0 | 1126.7 | 408.0 | yes |
| Greedy | 555 | 514 | 1114 | 1154.7 | 435.9 | yes |
| Single-period MILP | 510 | 489 | 1075 | 1086.9 | 368.2 | yes |
| **MPC** | 238 | 213 | 1096 | **740.3** | **21.6** | yes |
| Oracle (upper bound) | 232 | 211 | 1058 | 718.7 | 0.0 | yes |

## Findings

- **MPC is the best feasible policy** — the multi-period look-ahead roughly halves shortage+overflow
  vs single-period MILP, and lands within 3% of the perfect-foresight Oracle (regret 21.6).
- **Single-period MILP** helps modestly over No Action, but myopic optimisation leaves most of the
  value on the table — quantifying why multi-period decisioning matters.
- **Greedy can be net-harmful**: it relocates 1,114 units but, with these cost weights, the
  reposition spend outweighs the imbalance it relieves, so it costs slightly more than doing
  nothing. An honest reminder that "any rebalancing" is not automatically good.
- Every policy is feasibility-checked each period (0 infeasible periods); Oracle bounds them all.

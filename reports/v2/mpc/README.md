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
  nothing. A reminder that "any rebalancing" is not automatically good.
- Every policy is feasibility-checked each period (0 infeasible periods); Oracle bounds them all.

## Computational cost (reproduce: `make v2-mpc` → `python -m optimization.mpc_run --timing`)

| Policy | wall (72h) | ms/hour | per-hour complexity | solve |
|---|---|---|---|---|
| No Action | ~0.001s | ~0.01 | O(N) | none |
| Greedy | ~0.01s | ~0.2 | O(N²·V) arithmetic | none |
| Single-period MILP | ~0.8s | ~11 | MILP(N² int vars) | HiGHS ×1 |
| **MPC (this design)** | ~0.7s | ~10 | MILP(N²) + O(N·H) cumsum | HiGHS ×1 |
| "Classical" joint-horizon MPC | — | ~H× larger | MILP(H·N² vars) | HiGHS ×1 (H× bigger) |

**Key point — MPC here costs the same as single-period MILP (≈0.7–0.9×), not H× more.** The
look-ahead is encoded in the *target* (a cheap `O(N·H)` cumulative sum of the forecast), then the
same-size per-period MILP places the moves. So the 34% cost reduction (1127→740) comes at
essentially **zero extra compute** vs the myopic MILP. The usual "MPC is expensive" penalty
(`H×` more variables) applies only to *classical* joint-horizon MPC that optimises `u_t…u_{t+H-1}`
together; this design trades a little theoretical optimality for that saving and still lands within
3% of Oracle.

Operationally the decision is made once per hour and takes ~10 ms — a ~360,000× real-time margin —
so solve time is **not** the binding constraint; forecast quality is. At real scale (hundreds of
stations) the MILP's `N²` integer variables dominate; standard mitigations: sparsify to nearby
pairs (`N²→N·k`), warm-start, aggregate to H3 zones, keep `H` small.

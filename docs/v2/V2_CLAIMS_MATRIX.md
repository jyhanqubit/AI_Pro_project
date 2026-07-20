# V2 Claims Matrix & Result Envelope

Every V2 API response and UI metric must be traceable to an artifact and honestly labeled. This
doc defines the **result envelope** and holds the **claim matrix** (currently all `pending`).

## Result envelope

Every surfaced result — forecast, ledger figure, policy comparison, pricing recommendation,
Copilot answer — carries:

```jsonc
{
  "value": 0.0,                 // the number/string being claimed (or null if unavailable)
  "run_id": "run_...",          // the execution that produced it
  "artifact_id": "reports/v2/.../file.json#pointer",  // where it is persisted
  "mode": "demo_fixture",       // demo_fixture | historical_replay | live | research
  "claim_status": "pending_live_label",
  "freshness": "2026-07-20T00:00:00Z"  // when the backing artifact was produced (tz-aware)
}
```

Rules:
- A numeric value with no `artifact_id` is not renderable in non-demo modes.
- `mode` and `claim_status` are independent: a `historical_replay` result can be `measured`;
  a `live` result may still be `pending_live_label` until delayed labels arrive.
- `demo_fixture` heuristics may set `claim_status: demo_fixture` and must never appear in
  `live`/`historical_replay`/`research` surfaces.

## `claim_status` taxonomy

| status | meaning | may drive product decision? |
|---|---|---|
| `measured` | produced by a real holdout/experiment on real data | yes |
| `offline_benchmark` | measured on a fixed offline benchmark set | yes (offline) |
| `simulated` | model/policy simulation, no real users | for comparison, not as causal result |
| `pending_live_label` | awaiting delayed ground-truth labels | shown as pending |
| `assumption` | from the versioned assumption set (cost/elasticity) | as an input, labeled |
| `blocked_data` | needed data not yet collected/gated | shown as blocked, no number faked |
| `blocked_external` | external dependency unavailable (rate-limit, key) | shown as blocked |
| `demo_fixture` | deterministic demo heuristic | demo mode only |
| `research` | research-only (RL/QAOA/etc.) | never feeds product surfaces |

## Claim matrix (current)

> All rows are `pending` until the owning phase produces a real artifact. Do not populate a cell
> from v1 numbers or estimates — only from `reports/v2/**`.

| Claim | Phase | Artifact (target) | claim_status | Value |
|---|---|---|---|---|
| Promoted measured model artifact exists + loadable for serving | V2-01 | `reports/v2/holdout/promoted_model.json` | **measured** | `hist_gradient_boosting` (lr=0.05, depth=8, iters=600), served via `ml/forecasting/promoted.py`; API wiring → V2-07 |
| H3 multi-holdout WAPE (aggregate, 3 rolling windows, JC 2024) | V2-01 | `reports/v2/holdout/h3_multiholdout.json` | **measured** | WAPE **0.4828 ± 0.0030**, MASE **0.7996 ± 0.0186**, beats B0 ~0.648 |
| No-Event vs Rule-Event vs LLM-Event lift | V2-03 | `reports/v2/llm_value/incremental_value.json` | **blocked_data** (`insufficient_event_overlap`) | ΔWAPE=0, CI[0,0] all arms; arms identical on test (event coverage 0.3%) — honest null |
| LLM incremental cost | V2-03 | `reports/v2/llm_value/incremental_value.json` | **measured** (mock $0) + **assumption** (est real) | actual $0 (mock); est real $0.0061/371 articles; net LLM value −$0.01 |
| Predictive lift → profit/regret | V2-02 | `reports/v2/ledger/profit_regret.json` | **simulated** ($ assumption-conditioned; units measured) | Promoted forecast nets **+$103,271** vs seasonal-naive over 114,079 zone-hours; sign positive across all 9 cost settings; regret vs Oracle $218,697 |
| MPC vs No-Action/Greedy/MILP | V2-04 | `reports/v2/mpc/policy_comparison.json` | pending | — |
| Pricing sensitivity + guardrail audit | V2-05 | `reports/v2/pricing/` | pending | — |
| Copilot correctness + relevance | V2-06 | `reports/v2/copilot/correctness_benchmark.json` | pending | — |
| All UI metrics resolve to artifacts | V2-07 | UI ↔ `reports/v2/**` | pending | — |

The V2-09 final audit fills this matrix from committed artifacts and mirrors it into
`reports/v2/final/claim_matrix.json`.

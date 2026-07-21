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
| Structured event feed lift (permitted) | V2-03 | `reports/v2/llm_value/incremental_value_borough.json` | **measured** | Borough/NYC 19.9M trips, test May: A1−A0 WAPE 0.1069→0.1047, CI [1.87,5.88], +$33k — structured events help (reproduces v1) |
| LLM-from-news incremental value | V2-03 | `reports/v2/llm_value/incremental_value_borough.json` | **measured (negative)** | Real Claude extraction (23 clean NYC events, 336 test rows), test May: A2−A1 WAPE 0.0883→0.0905, CI [−5.32,−1.56], **net LLM value −$17,789**. Net-negative even with high-quality LLM extraction — news redundant vs structured feed, not a mock artifact |
| **LLM Feature Value metric** (did LLM features improve accuracy?) | V2-03 | `reports/v2/llm_value/incremental_value_borough.json#llm_feature_value_metric` | **measured** | Decision-grade metric = relative WAPE reduction on the **LLM-active subset** + block-bootstrap CI. Old flat-box feature: **`MEANINGFUL_NEGATIVE`**, −5.52%, CI [−17.51, −0.98], n=336 → measurably degrades. Pre-declared thresholds (1% effect + CI≠0); pure fn, 6 unit tests |
| Improved LLM feature + graph contribution | V2-03 | `reports/v2/llm_value/graph_contribution.json` | **measured (null)** | Fixed feature engineering (event-time anchor, half-life decay, type-scoped boroughs). Improved feature A2−A1: **`NO_MEANINGFUL_EFFECT`** −0.4%, CI [−4.90,1.36] — **harm removed** (was −5.52%), now neutral. Graph A3−A2: **`NO_MEANINGFUL_EFFECT`** −1.32%, CI [−3.76,0.72] — **graph NOT proven at borough grain** (coarse: 5 zones). Fair venue = H3-zone grain, not yet run. Not faked positive |
| "News→permit-DB" reconstruction | V2-03 | `reports/v2/llm_value/permitize_contribution.json` | **measured (hypothesis refuted)** | LLM rebuilt news as permit-schema records (precise time+borough). permitized−A1 **`MEANINGFUL_NEGATIVE` −6.31%** CI [−25.2,−5.5]; worse than raw news too. **Structure is NOT the missing ingredient** — permit feed's value is event DENSITY (63,070 events) vs news's ~19; precise features on sparse events = confident noise. 4 events leakage-dropped (retrospective). Honest negative |
| News-as-importance-weight on permit feed | V2-03 | `reports/v2/llm_value/importance_weight_contribution.json` | **measured (negative)** | ev_active×(1+news_salience) — modulate dense permit feed, untouched where no news. **`MEANINGFUL_NEGATIVE` −7.82%** CI [−25.6,−5.9] (WAPE 0.0883→0.0925). Top example: Winter Storm Fern amplifies permit 63→119.7, but blizzards SUPPRESS demand → wrong-signed. "Newsworthy" ≠ "more demand"; sign heterogeneous, ~191 rows unlearnable |
| H3-grain graph contribution (fair venue) | V2-03 | — | **blocked_data** | Fine H3 graph test needs geocoded events; real permit/news events are borough-tagged only (no lat/lng; geocoding needs external data). Not fabricated. Borough-grain graph test (null) is finest fair real-data test |
| LLM incremental cost | V2-03 | `reports/v2/llm_value/incremental_value.json` | **measured** (mock $0) + **assumption** (est real) | actual $0 (mock); est real $0.0061/371 articles; net LLM value −$0.01 |
| Predictive lift → profit/regret | V2-02 | `reports/v2/ledger/profit_regret.json` | **simulated** ($ assumption-conditioned; units measured) | Promoted forecast nets **+$103,271** vs seasonal-naive over 114,079 zone-hours; sign positive across all 9 cost settings; regret vs Oracle $218,697 |
| MPC vs No-Action/Greedy/MILP | V2-04 | `reports/v2/mpc/policy_comparison.json` | **simulated** | Ledger cost (lower better): NoAction 1127 / Greedy 1155 / MILP 1087 / **MPC 740** / Oracle 719. MPC best feasible, regret 21.6 (~3% of Oracle); all feasible |
| Pricing sensitivity + guardrail audit | V2-05 | `reports/v2/pricing/{guardrail_audit,sensitivity}.json` | **simulated** | 576 zone-hours: 0 guardrail violations, safety base-fare, budget respected, negative control passes; A/A CI covers 0 (design valid). Shadow quotes only |
| Copilot correctness + relevance | V2-06 | `reports/v2/copilot/{correctness,graphrag,neutral_retrieval}_benchmark.json` | **offline_benchmark** | **Typed-tool**: 20 Q, real claude routing 1.0/1.0/1.0, halluc=0 (keyword 3, FAIL). **GraphRAG @ scale** (real graph 2,895 events): vs a fair flat-retrieval baseline (6/21, refuses 6/6, 0 halluc) GraphRAG is 21/21 — but task is graph-structural so graph is high BY CONSTRUCTION. **Neutral text-lookup counterpart** (12 Q, method-independent gold): flat_text 0.833 top1 **beats** graph_boosted 0.750 — graph gives NO lift on text. The pair bounds the honest verdict both ways (match tool to query type). **RAGAS retrieval** (real ragas 0.4.3 non-LLM: ctx-precision flat 0.833 vs graph 0.771, recall tied) agrees. **RAGAS generation-side** judged in-session (no LLM key): faithfulness **1.0**, answer_relevancy **0.985** over 10 answered Q; verdicts committed to a fixture, drift-guarded. This pass caught + fixed a mislabel (llm_news_value dollar figure `measured`→`simulated`) |
| All UI metrics resolve to artifacts | V2-07 | UI ↔ `reports/v2/**` | pending | — |

The V2-09 final audit fills this matrix from committed artifacts and mirrors it into
`reports/v2/final/claim_matrix.json`.

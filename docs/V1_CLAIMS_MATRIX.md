# ShockFlow AI V1 — Claims Matrix

What may be claimed, under what state, gated by what. Enforced in code by
`contracts/v1/enums.py::ClaimState` and `config/v1/claims.yaml`.

| Artifact | claim_state | May claim | Gate / condition |
|----------|-------------|-----------|------------------|
| `ForecastPair` (M1 vs M1-zero) | `pending` → `measured` | "model-attributed event delta" | measured only after real label links (`ScoredForecastPair.actual`) |
| Event-lift metrics | `measured` | "news/graph reduces holdout error" | event_lift_gate: non-zero test event features, same split/target, **real** news + labels, paired comparison, uncertainty interval |
| Live prediction | `pending` | prediction exists | label not yet arrived → `pending_label`; never scored until real label |
| `AnomalyAlert` | `measured` / synthetic-flagged | "anomaly detected" | `is_synthetic_fault=true` excluded from real-incident precision/recall |
| `RecommendationResult` | `simulated` (offline) | ranking quality on historical-choice labels | no selected-station leakage; chronological split; as-of features |
| `IncentiveQuote` / policy sim | `simulated` | operating-cost/uplift **estimates** | `is_simulated=true` + "SIMULATED OUTCOME — NOT A LIVE BUSINESS RESULT" |
| Experiment result | `simulated` / `dry_run` | design correctness (A/A, SRM) | **causal lift** only for `actual_experiment` with real users |
| QUBO / QAOA | `research` | research feasibility mapping | never fed to serving; simulator ≠ hardware; no quantum-advantage claim |

## Forbidden (invariant list, V1_Prompt §4)

- Fabricated metric / latency / KPI / accuracy / uplift.
- GBFS inventory delta used as a demand label.
- Calling a forecast/model comparison an A/B test.
- Presenting a simulation as a live business result.
- Attention weights presented as user-facing explanations (use reason codes).
- Breaking a v0 contract without a documented migration.
- Future (post-cutoff) data in any feature.

## Current disabled claims (this environment)

No public internet / live LLM → **real-news accuracy & event-lift claims are DISABLED** until the
GDELT/live path is genuinely available. Recommendation/policy/experiment numbers, when produced, are
**simulated** and labelled as such.

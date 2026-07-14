# ShockFlow AI V1 — Architecture

> Status: **V1-00 scaffold.** Boxes marked _(planned)_ are contracts/skeletons only.

## 1. Data & serving flow

```text
news (fixture | GDELT-planned)
  → ArticleRecord ─(dedup: url_hash/title_hash)→ backfill store        [V1-01]
  → EventRecordV1 (LLM extract, evidence-gated)                        [V1-02]
  → incremental graph feature refresh (affected zones only)            [V1-02]
  → M0/M1/M1-zero dual inference → ForecastPair (claim_state)          [V1-03]
      ├→ Event-Lift evaluation (paired, CI)                            [V1-04]
      ├→ Anomaly detection + root cause → AnomalyAlert                 [V1-06]
      └→ Recommendation: filter → dual-encoder retrieve → cross-attn
         rerank → policy(+incentive) → RecommendationResult            [V1-07A..D]
  → Clustered-switchback experiments (simulated/dry-run)               [V1-08]
  → UI: 5 screens + offline E2E                                        [V1-09]
```

Live-shadow variant runs the same chain on a 15-min micro-batch with predictions held as
`pending_label` until delayed Trip-History labels arrive _(planned, V1-05)_.

## 2. Backward compatibility

V1 is **additive**. v0 packages (`contracts/`, `services/api/`, `pipelines/`, `ml/forecasting/`,
`optimization/`, `apps/web/`) are untouched except by explicit, documented migrations. V1 code lives
under `contracts/v1/`, `config/v1/`, and new `ml/*` / `pipelines/*` submodules. The v0
`OperatingMode` (4 values) stays valid; `OperatingModeV1` (6 values) is its superset.

## 3. Model registry _(planned, V1-03)_

Artifacts keyed by `(model_version, feature_version, train_window_id, seed)`. `ForecastPair`
carries all four. `degraded_demo` heuristic fallback fires **only** when an artifact is absent, and
is labelled as such (never presented as a measured model).

## 4. Recommendation stack _(planned, V1-07)_

`ShockFlowRecFormerRetriever` (attention dual encoder, L2-normalised embeddings, ExactTorchIndex
default; FAISS optional) → `ShockFlowRecFormerReranker` (cross-attention) → feasibility + business
policy → Top-3. Index cache key includes cutoff, model/feature/event-feature versions, station
snapshot hash. Explanations are `ReasonCode`s, not attention weights.

## 5. Planned API endpoints (contract-only in V1-00)

| Endpoint | Purpose | Phase |
|----------|---------|-------|
| `POST /v1/recommendations/stations` | RENT/RETURN Top-K with reason codes | V1-07C |
| `POST /v1/recommendations/compare-event-impact` | event ON/OFF frozen-candidate rank delta | V1-07C |

v0 endpoints (`/v1/forecasts`, `/v1/rebalancing/solve`, …) keep their contracts.

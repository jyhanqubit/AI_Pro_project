# ShockFlow AI V1 — Evaluation Protocol

> Status: **protocol defined (V1-00).** Metrics are produced only by executed runs in later phases.

## 1. Temporal discipline (unchanged from v0, extended)

- Rolling-origin / expanding-window only; **random K-fold is forbidden** for forecasting and
  chronological split for recommendation.
- As-of features only: `available_at <= cutoff`. Leakage regression tests are mandatory and never
  weakened.
- All ablation arms share identical cutoffs, splits, target, and tuning budget.

## 2. Event-lift (V1-04) — does news/graph reduce error?

Ablation `B0 seasonal-naive · B1 history+calendar · B2 +raw news volume · B3 +LLM event features ·
B4 +graph-spatial`. Report:

- overall WAPE / MAE / MASE; event-window WAPE; peak-direction accuracy; interval coverage when available;
- **paired** zone-hour error differences; day/week block-bootstrap 95% CI;
- results sliced by event type / confidence / radius.

Artifacts under `reports/v1/event_lift/`. A non-improvement is reported and analysed, never hidden.

## 3. Recommendation (V1-07)

- Retrieval: Recall@5/10/20, MRR@20, NDCG@20; RENT/RETURN split; event-window Recall@20; seen vs cold-start.
- End-to-end: HitRate@1/@3, MRR, NDCG@3, feasible@3, no-feasible rate, average detour, event-window NDCG@3.
- Ablations `R0..R4` (nearest → heuristic → MLP → dual-encoder w/o event → w/ event) and `E0..E3`
  (event in retriever/reranker/forecast-delta). Freeze the candidate set for accuracy comparisons.
- Latency: p50/p95 retrieval / rerank / E2E, from real executed runs.

## 4. Claim gates

Numbers are surfaced only when the corresponding gate in `config/v1/claims.yaml` is satisfied by a
real run (non-zero test event features, same split/target, real news + labels, paired comparison,
uncertainty interval). Otherwise the claim is disabled and the artifact keeps a non-measured
`claim_state`.

## 5. Anomaly (V1-06)

False alerts/day, precision@K on a labelled/reviewed fixture, mean-time-to-detect, known-event recall.
Synthetic faults are flagged `is_synthetic_fault=true` and excluded from real-incident claims.

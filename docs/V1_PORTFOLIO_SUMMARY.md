# ShockFlow AI V1 — Portfolio Summary

Event-aware urban mobility demand forecasting + fleet decision support, extended in V1 with a
measured model story, a rider-facing recommendation/pricing stack, live-shadow serving, anomaly
detection, experimentation, and a FAISS news vector store — all **offline-reproducible** and held to
a strict honesty boundary (measured / pending / simulated / blocked).

## What a reviewer can run offline

```text
fixture/GDELT news → backfill + coverage gate → event extraction → event graph
  → as-of graph features (incremental == full rebuild) → M0/M1/M1-zero (measured B0-B4)
  → recommendation (dual-encoder retriever + cross-attn reranker + policy)
  → dynamic-incentive policy simulation → clustered-switchback experiments
  → anomaly detection + root cause → live-shadow pending predictions
  → 8-screen operator/rider console
```

## Highlights (measured, on real JC-202606 data)

- **Forecasting** — history+calendar (M0) cuts WAPE 0.658→0.516 vs seasonal naive; event/graph
  features add **no measured lift** on this data (events don't overlap the eval window) — reported
  honestly, not hidden.
- **Recommendation** — dual-encoder retriever Recall@20 **0.952**; end-to-end HitRate@3 **0.754**,
  feasible@3 **1.00**, p50 latency ~16 ms. Open-retrieval setting (not directly comparable to the
  radius baselines) — stated plainly.
- **Rebalancing** — MILP optimum == enumeration; greedy always feasible.
- **Experiments** — clustered switchback; A/A CI contains 0 (design validated); treatment effects are
  **simulated**, never a causal lift.
- **Anomaly** — 4 detector families; synthetic faults detected with **zero false alerts** on clean
  data; a depletion is root-caused to a source event with article evidence.

## The honesty boundary (the point of the project)

| Surface | Claim state |
|---------|-------------|
| Forecast ablation (B0-B4) | measured |
| Event lift | `insufficient_event_overlap` — claim disabled |
| Real-news coverage | `BLOCKED_DATA` until a real backfill passes the gate |
| Live-shadow predictions | `pending` until delayed labels arrive |
| Recommendation / pricing / experiments | `simulated` — never a live business result |
| QUBO / QAOA | research-only; simulator, no advantage claim |

## Web console (8 screens)

자전거 찾기 (rider) · 수요 급증 원인 · 뉴스 검색 (FAISS) · 시나리오 비교 · 재배치 계획 · 모델 Lift ·
이상 탐지 · 실험 랩. Historical Replay vs Live are visually distinct; every KPI is measured or
explicitly labelled simulated.

## Reproduce

`make install` → `make test` (199 passed, 1 skipped) → `make api` + `make web`. Full V1 detail:
`docs/V1_*`, `reports/v1/V1_FINAL_AUDIT.md`, `docs/V1_EXECUTION_LOG.md`.

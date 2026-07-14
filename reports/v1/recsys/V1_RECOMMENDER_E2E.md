# V1-07C — Cross-Attention Reranker + Policy + Serving (measured)

End-to-end recommender: **Filter → Dual-Encoder Retrieve (Top-20) → Cross-Attention Rerank →
Feasibility & Policy → Top-3**, measured on **real** JC-202606. Reproduce:
`make evaluate-recommendation-e2e` (writes `reports/v1/recsys/e2e_metrics.json`).

## Run manifest

- 219,407 RENT/RETURN samples; chronological split; retriever + reranker trained on bounded slices
  (retriever 4,000; reranker 4,000; 2 epochs — **logged caps**), evaluated on 3,000 test queries.
- Reranker: listwise softmax CE, retriever frozen; positive is in-list (force-in **train only**).
- Event/inventory/forecast tokens absent on plain trip data → `insufficient_event_overlap`
  (E0–E3 collapse; no event lift claimed).

## Measured end-to-end metrics (test = 3,000)

| Metric | Value |
|--------|-------|
| HitRate@1 | 0.636 |
| HitRate@3 | 0.754 |
| MRR | 0.693 |
| NDCG@3 | 0.709 |
| feasible@3 | **1.000** |
| no-feasible rate | **0.000** |
| avg detour | 0.413 km |
| latency p50 / p95 | 15.6 ms / 19.0 ms |

## Honest reading

- **Open-retrieval setting.** The pipeline retrieves over **all 251 stations** (retriever
  Recall@20 = 0.952, `V1_RETRIEVER_REPORT.md`), so ~5% of positives are lost before reranking — an
  upper bound on end-to-end recall. Within the retrieved slate the reranker+policy reach HitRate@3
  = 0.75. This is a *harder* setting than the radius-candidate baselines (B0 HitRate@3 ≈ 0.99 over
  ~10 nearby stations), so the numbers are **not** directly comparable.
- **feasible@3 = 1.0, no-feasible = 0.0**: infeasible candidates are removed before ranking (never
  penalised); every surfaced station is feasible by construction.
- **No event lift is claimed** — events do not overlap this data; the ablation records
  `insufficient_event_overlap`. Real value from event/inventory signal awaits V1-01 news overlap.

## Serving & API

- `POST /v1/recommendations/stations` → Top-3 with per-component scores + reason codes.
- `POST /v1/recommendations/compare-event-impact` → event ON/OFF Top-3 overlap (frozen candidates).
- Both labelled `operating_mode=policy_simulation`, `claim_state=simulated`; a small model trained on
  the bundled sample fixture, never presented as the measured model. Degrades to HTTP 503 if the
  `[recsys]` extra is absent (no fabricated result).

## Tested (`tests/unit/test_recsys_reranker.py`, `tests/integration/test_api.py`)

- Reranker forward + listwise/pairwise loss; policy removes infeasible & returns
  `no_feasible_candidate`; component scores kept separate; reason codes emitted; serving Top-3 all
  feasible; event ON/OFF identical with no overlap; API endpoints return simulated results.

# V1-07B — ShockFlowRecFormerRetriever (measured)

Attention dual-encoder retriever (PyTorch) with ExactTorchIndex Top-K, evaluated on **real**
JC-202606 Trip History. Reproduce: `make train-recommendation-retriever`
(writes `reports/v1/recsys/retriever_metrics.json`). Deterministic given seed + inputs.

## Run manifest

- Data: 109,897 trips → 219,407 RENT/RETURN samples; chronological split.
- Train (bounded for CPU, **logged**): 6,000 of 175,526 train samples, 2 epochs. Eval: 8,000 of
  43,881 test rows (`TEST_EVAL_CAP`). 251 stations in the effective master.
- Model: d_model=96, 2 layers, 4 heads, temperature=0.07, InfoNCE over deduplicated
  positive+hard-negative station columns (duplicate-positive false negatives avoided by construction).
- Event/forecast/inventory tokens absent on plain June trip data → **`insufficient_event_overlap`**;
  R3(no-event) == R4(event). No event lift is claimed.

## Measured metrics (open retrieval over all 251 stations; test = 8,000)

| Model | Recall@5 | Recall@10 | Recall@20 | MRR@20 | NDCG@20 |
|-------|----------|-----------|-----------|--------|---------|
| **R4 dual encoder** | 0.835 | 0.922 | **0.952** | 0.582 | 0.671 |
| cold-start (n=5) | — | — | 0.400 | — | — |

Latency (CPU): embed **0.21 ms/query**, exact search **0.003 ms/query** (251-vector index).

## Reading (no fabricated lift)

- **Not an apples-to-apples win over the baselines.** The retriever does *open* Top-K over **all 251
  stations**; the B0–B3 baselines (`V1_RECSYS_BASELINES.md`) rank within a **radius-filtered
  candidate set** (~10 stations), where B0 nearest trivially reaches R@20≈1.0. The two candidate sets
  differ, so the numbers are **not** directly comparable, and the retriever's job is strictly harder.
- **Geography still dominates.** Without event/inventory/forecast signal overlapping this data, the
  chosen station is almost always the nearest — a bias pure distance already captures. The dense
  retriever recovers most of this (R@20 0.95) but adds **no measured value yet** over nearest.
- **Where it should help (future):** event-window and inventory-constrained queries, once real news
  overlaps the demand window (V1-01) and inventory coverage improves. Until then the event ablation
  is `insufficient_event_overlap`, by design.

## Acceptance criteria (tested — `tests/unit/test_recsys_retriever.py`)

- ExactTorchIndex == manual brute force; masks applied (padded events & missing optional features
  ignored); same checkpoint+input → same score; stale index (changed cutoff/version/snapshot)
  detected; InfoNCE trains.

# V1-07A — Recommendation Baselines (measured)

Context-aware station recommendation (RENT/RETURN), evaluated on **real** Citi Bike Jersey City
June 2026 Trip History. Reproduce with `make evaluate-recommendation` (writes
`reports/v1/recsys/metrics.json`). Deterministic given data + config + seed=42.

## Run manifest

- Data: `JC-202606` — **109,897 trips → 219,407 RENT/RETURN samples**.
- Split: chronological (latest 20% test) → train 175,526 / **test 43,881**. No random split (§13).
- Labels: the historically chosen station is the positive; query is that station's coordinate with
  deterministic ≤150 m jitter (`query_is_synthetic=true`,
  `label_source=historical_choice_with_synthetic_query`). The chosen station id is never a query feature.
- Inventory: GBFS fixture covers only the demo stations → **inventory unknown for 98% of candidates**
  (`inventory_missing_rate = 0.98`), carried as an explicit mask, never fabricated.
- B3 MLP trained on the first 8,000 train samples (`MLP_TRAIN_SAMPLE_CAP`, logged — not hidden).

## Measured metrics (test = 43,881 queries)

| Baseline | HR@1 | HR@3 | MRR | NDCG@3 |
|----------|------|------|-----|--------|
| **B0 nearest feasible** | **0.845** | **0.986** | **0.915** | **0.931** |
| B1 distance + capacity | 0.816 | 0.977 | 0.897 | 0.913 |
| B2 distance + risk + benefit | 0.827 | 0.980 | 0.903 | 0.920 |
| B3 MLP pair scorer (sklearn) | 0.842 | 0.983 | 0.912 | 0.928 |
| candidate coverage | 10.6 stations/query · positive-in-candidate rate = 1.00 | | | |

## Honest reading (non-improvement reported, §13 / invariant 15)

- **Pure distance (B0) is the strongest baseline here.** With inventory unknown for 98% of
  candidates, the capacity- and risk-aware heuristics (B1/B2) have little real signal and do **not**
  beat B0. The sklearn MLP (B3) essentially recovers B0 (0.842 vs 0.845) rather than exceeding it.
- This is expected and is the motivation for V1-07B/C: a learned dual-encoder + reranker with
  event/forecast tokens should help most on **event-window** queries and when inventory is present —
  not on ordinary "nearest station" choices where distance already explains the label.
- No metric is claimed beyond what this executed run produced. Any future retriever/reranker number
  must beat B0 on this same split to be surfaced.

## Leakage & determinism guards (tested — `tests/unit/test_recsys.py`)

- Chosen station id excluded from query features; chronological split has no future leak;
  dataset is deterministic; positive is always within the candidate set.

# ShockFlow AI V1 — Execution Plan

Incremental, backward-compatible build on top of v0 (`VERSION = v0`, git `35404e3`). Each phase is
the smallest complete vertical slice; v0 tests must stay green throughout (invariant 12).

| Phase | Goal | Key files | Acceptance | Depends on |
|-------|------|-----------|------------|------------|
| **V1-00** Contract migration & audit | Add V1 modes, claim boundary, contract skeletons + docs without touching v0 | `contracts/v1/*`, `config/v1/*.yaml`, `docs/V1_*.md` | v0 tests pass; measured/pending/simulated/dry-run states in contracts; model-comparison ≠ experiment documented; no unbuilt endpoints documented as built | — |
| **V1-01** Historical news backfill & coverage gate | Overlap real demand window with real news; non-zero event-feature coverage | `pipelines/collectors/gdelt_*`, coverage report | Idempotent backfill; no post-cutoff leakage; reproducible manifest; gate pass/fail in artifact | V1-00 |
| **V1-02** Real event extraction & incremental graph features | Wire article metadata → extractor → incremental features | `pipelines/events/*`, `pipelines/features/*` | Evidence-gated events; idempotent upsert; incremental == full rebuild; future-exclusion test | V1-01 |
| **V1-03** Model registry & dual inference (M0/M1/M1-zero) | Replace demo heuristic with real artifacts | `ml/registry/*`, serving hook | API returns real model version; deterministic; provenance to forecast | V1-02 |
| **V1-04** Event-lift evaluation | Does news/graph reduce holdout error? | `reports/v1/event_lift/*` | Paired comparison + CI on real news+labels; non-improvement | V1-03 |
| **V1-05** Live news shadow pipeline | 15-min micro-batch, pending_label | `pipelines/live/*` | Fixture stream E2E; live failure never breaks demo; real latency artifact | V1-03 |
| **V1-06** Anomaly detection & root cause | 4 detector families + attribution | `ml/anomaly/*` | Detects stale/impossible/depletion fixtures; event-linked explanation | V1-02 |
| **V1-07A** Recommendation contracts, dataset, baselines | Context-aware RENT/RETURN dataset + heuristics/MLP | `ml/recsys/*` | No selected-station leakage; chronological split; deterministic dataset | V1-03 |
| **V1-07B** Attention dual-encoder retriever | `ShockFlowRecFormerRetriever` | `ml/recsys/retriever/*` | ExactTorchIndex == brute force; masks applied; deterministic; version-keyed index | V1-07A |
| **V1-07C** Cross-attention reranker + policy + serving | `ShockFlowRecFormerReranker`, reason codes, API | `ml/recsys/reranker/*`, API | Infeasible removed; reason codes not attention; retrieval/rerank failures separated | V1-07B |
| **V1-07D** Dynamic incentive & policy simulation | Pickup/return credit, P0–P5 | `ml/pricing/*` | `is_simulated=true` on all; budget/fairness constraints; no RL on required path | V1-07C |
| **V1-08** Clustered switchback experimentation | Switchback design, A/A, ITT | `experiments/*` | A/A clean; SRM check; simulated/dry-run labelled; not called causal lift | V1-07D |
| **V1-09** UI, E2E, audit & packaging | 5 screens, golden path, final audit | `apps/web/*`, `reports/v1/V1_FINAL_AUDIT.md` | Offline E2E; actual/pending/simulated badges; docs/code sync | all |

## Offline-blocker policy (V1_Prompt §5)
No public internet / no live LLM in this environment → phases needing **real GDELT news** or a
**live LLM** run their deterministic fixture path and are marked `BLOCKED_DATA` / `BLOCKED_EXTERNAL`
for the *real-data* claim. No timestamps are shifted and no news is fabricated. Accuracy/lift claims
that depend on real news+labels stay **disabled** until the data path is genuinely available.

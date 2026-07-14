# ShockFlow AI V1 — Final Audit

Audit of the V1 build against the honesty invariants (V1_Prompt §4, §18, §20). Every claim below is
backed by an executed run or a test; anything not measurable on the current data is marked BLOCKED
and its claim is disabled — never fabricated.

## Phase status

| Phase | Status | Honest note |
|-------|--------|-------------|
| V1-00 Contracts & scaffold | PASSED | 6 modes + ClaimState + 11 contracts; v0 untouched |
| V1-01 News backfill & coverage gate | PASSED · real-news claim **BLOCKED_DATA** | GDELT live works (opt-in); fixture path default; gate honest |
| V1-02 Event extraction & incremental features | PASSED | incremental == full rebuild (verified) |
| V1-03 Model registry & dual inference | PASSED · event lift **0** | measured B0-B4; M1==M0 (no overlap) |
| V1-04 Event-lift evaluation | PASSED · gate **BLOCKED** | paired B4-B1=0, CI [0,0]; claim disabled |
| V1-05 Live-shadow pipeline | PASSED | micro-batches, pending_label, restart-safe |
| V1-06 Anomaly detection & root cause | PASSED | 4 detectors, 0 false alerts on clean data |
| V1-07A Rec dataset & baselines | PASSED | real JC-202606; B0 nearest strongest |
| V1-07B Dual-encoder retriever | PASSED | R@20 0.952; ExactTorchIndex==brute force |
| V1-07C Reranker + policy + serving | PASSED | E2E HitRate@3 0.754, feasible@3 1.0 |
| V1-07D Dynamic incentive & simulation | PASSED · **SIMULATED** | P0-P5; is_simulated=true |
| V1-08 Clustered switchback experimentation | PASSED · **SIMULATED** | A/A CI contains 0; not a causal lift |
| V1-09 UI, E2E, audit, packaging | PASSED | 8 web screens; offline golden-path E2E |

Extra infra: **FAISS vector store** (accumulating news, semantic search, same-event clustering) +
recsys FaissIndex.

## Audit checklist (V1_Prompt §18)

- **Temporal leakage** — as-of `available_at <= cutoff` enforced in contracts, features, incremental
  refresh, and the shadow stream. Tests: 13:59 vs 14:00 boundary, future-event exclusion. ✓
- **Model artifact vs heuristic** — the demo forecaster is the labelled `demo-heuristic-v1`; the
  measured model story (B0-B4) is separate and surfaced in Model Lift Lab. ✓
- **Live pending label** — shadow predictions carry `claim_state=pending` until real labels arrive. ✓
- **Historical vs simulation metrics** — recommendation/experiment/policy outputs are `simulated`;
  forecast ablation metrics are `measured`; both labelled distinctly. ✓
- **Recommendation label limitations** — historical-choice labels with synthetic-query jitter, flagged
  `query_is_synthetic=true`; no selected-station leakage (tested). ✓
- **Retrieval / reranking failure separation** — surfaced separately in serving; open-retrieval vs
  radius-baseline caveat documented (not a false win). ✓
- **Pricing fairness / budget feasibility** — credits ≥ 0 (no surcharge), hard budget cap, zone
  fairness measured (no protected attributes). ✓
- **Experiment propensity & interference** — clustered switchback (zone×time), balanced propensity
  0.5, SRM check, cluster block-bootstrap CI, A/A validation. ✓
- **API / OpenAPI consistency** — Pydantic request/response models; endpoints return mode/claim/version. ✓
- **Docs / code synchronization** — `docs/V1_*`, `docs/STATUS.md`, execution log, this audit updated. ✓
- **One-command demo** — `make` targets per phase; offline golden-path E2E (`tests/e2e`). ✓

## Disabled claims (data/environment)

- **Event lift / event accuracy** — DISABLED (`insufficient_event_overlap`): curated events (Jul-12)
  postdate the June eval window, so event features are all zero. Unlock: collect overlapping June
  news (`make v1-collect-news-live`) → retrain → re-run V1-04.
- **Real-news coverage** — `BLOCKED_DATA` until a real GDELT backfill passes the coverage gate.
- **Causal lift** — never claimed; all policy/experiment effects are SIMULATED.

## Reproduce

`make test` (199 passed, 1 skipped) · `make api` + `make web` · `tests/e2e/test_v1_golden_path.py`.
Optional extras: `pip install -e .[recsys,vectorstore]` for the retriever + FAISS surfaces.

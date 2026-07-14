# ShockFlow AI V1 — Execution Log

Status vocabulary: `TODO | IN_PROGRESS | PASSED | BLOCKED_EXTERNAL | BLOCKED_DATA | FAILED | DEFERRED_OPTIONAL`.
Read this file to resume after any context compaction.

## Baseline regression (before any V1 change)
- Repo: git `35404e3`, `VERSION=v0`.
- Python `.venv` 3.10.0, Node v24.18.0.
- `pytest -q` → **115 passed, 1 skipped** (qiskit QAOA skip; documented). Native h3 "access violation"
  lines are a Windows warning, not failures.
- Web `tsc --noEmit` → pass.
- Note: v0 API user-facing `note` strings were localised to Korean earlier this session
  (`services/api/app.py`); no contract/schema change, tests unaffected.

## Phase status

| Phase | Status | Notes |
|-------|--------|-------|
| V1-00 Contract migration & audit | **PASSED** | Added `contracts/v1/*` (6 modes, ClaimState, 11 contracts), `config/v1/*.yaml`, `docs/V1_*.md`. v0 untouched; v0 tests still green. New contract tests added. |
| V1-01 Historical news backfill & coverage gate | **PASSED (real-news claim BLOCKED_DATA)** | `config/backfill.py` + `pipelines/collectors/{backfill,coverage,backfill_demo}.py`. NewsProvider interface: `FixtureNewsProvider` (offline default) + `GdeltNewsProvider` (disabled → degraded, no fabricated data). Ontology+city filter, url+title-hash dedup, **restart-safe checkpoint (idempotent)**, coverage report (§7 fields; event/feature fields null until V1-02), coverage gate. Demo: raw 4 → accepted 3, gate passes. Real GDELT offline → real-news accuracy claim **BLOCKED_DATA** (no timestamp shifts). 8 tests. `make v1-backfill-news`. |
| V1-02 Real event extraction & incremental features | **PASSED** | Reuses v0 `extract_events` (evidence grounding, confidence quarantine, dedup) + idempotent graph upsert. Added `pipelines/features/incremental.py`: `affected_zones` (new-event zones + zones within `radius_km` of an event or its `max_hops` neighbour centres, as-of filtered) + `refresh_incremental` — recomputes only affected zones, keeps the rest. **Incremental == full rebuild** verified (new-zone, same-zone, future-exclusion). `make v1-build-event-features`. 4 tests. |
| V1-03 Model registry & dual inference | **PASSED (event lift 0 — insufficient_event_overlap)** | `ml/forecasting/registry.py` surfaces the measured Phase-06 ablation as M0(B1)/M1(B4)/M1-zero(≈B1). `GET /v1/model/lift` + web **Model Lift Lab** (`/model-lift`). Measured: B1 beats B0 (WAPE 0.658→0.516) but B2-B4 == B1 (event_features_zero verified) → **model-attributed event lift = 0**, flagged honestly (not fabricated). Unlock path documented (collect overlapping June news → V1-04). 3 tests. |
| V1-04 Event-lift evaluation | TODO | Claim gated on V1-01 real news. |
| V1-05 Live news shadow pipeline | TODO | Fixture stream path; live disabled by default. |
| V1-06 Anomaly detection & root cause | TODO | |
| V1-07A Rec contracts/dataset/baselines | **PASSED** | `ml/recsys/*` + `config/recsys.py`. Real run on JC-202606 (109,897 trips → 219,407 samples, test 43,881). Measured B0–B3; **B0 nearest-feasible strongest (HR@1 0.845)** — capacity/MLP don't beat distance (inventory unknown 98%). Honest non-improvement reported in `reports/v1/recsys/V1_RECSYS_BASELINES.md`. 9 leakage/determinism tests. `make evaluate-recommendation`. |
| V1-07B Dual-encoder retriever | **PASSED** | `ml/recsys/{encoder,tokenize,index,retriever,retriever_eval}.py`. Multi-token attention dual encoder (d96/2L), MissingValueMaskEmbedding + event padding masks, InfoNCE (dedup columns → no false negatives), ExactTorchIndex (==brute force, version-keyed staleness). Measured on real JC-202606 (6k train/8k test, 251 stations): **R@20 0.952, MRR@20 0.582**; embed 0.21ms/q, search 0.003ms/q. Honest: open retrieval ≠ radius baselines; geography dominates, no measured lift yet; `insufficient_event_overlap` (R3==R4). 7 acceptance tests. `make train-recommendation-retriever`. See `reports/v1/recsys/V1_RETRIEVER_REPORT.md`. |
| V1-07C Cross-attention reranker + policy | **PASSED** | `ml/recsys/{reranker,policy,serving,reranker_eval}.py` + `services/api/recommendations.py` + endpoints. Cross-attn reranker (CLS/QUERY/SEP/STATION/6×PAIR, segment+pair-type emb), listwise CE (force-in train-only), policy layer (separated components + reason codes; infeasible removed → `no_feasible_candidate`). `/v1/recommendations/stations` + `/compare-event-impact` (simulated, 503-degrades w/o torch). Measured E2E on real data (3k queries): **HitRate@3 0.754, MRR 0.693, feasible@3 1.00, no-feasible 0.00**, detour 0.41km, p50 15.6ms. Honest: open retrieval ≠ radius baselines; `insufficient_event_overlap`. 5 unit + 2 API tests. `make evaluate-recommendation-e2e`. See `reports/v1/recsys/V1_RECOMMENDER_E2E.md`. |
| V1-07D Dynamic incentive & simulation | **PASSED** | `config/pricing.py` + `ml/pricing/{scenario,simulator,policies,evaluate}.py`. Pickup/return credit tiers (0..3, no surcharge); versioned deterministic choice simulator (`is_simulated=true`); P0-P5 (no-action/truck/static/dynamic/rec/hybrid) with budget hard-cap, max-detour, zone fairness. SIMULATED comparison: **P1 truck cheapest (net 7.7)**; dynamic credit fulfils but spends budget; static credit worst. 8 tests (no surcharge, budget cap, determinism, fairness). `make v1-policy-simulation`. See `reports/v1/pricing/V1_POLICY_SIM.md`. Recommendation track (07A-D) COMPLETE. |
| V1-08 Clustered switchback experimentation | **PASSED** | `config/experiment.py` + `ml/experiment/{switchback,engine,evaluate}.py`. Zone-cluster × time-block switchback (balanced phases → propensity 0.5), exposure/outcome/propensity logs, SRM, ITT + **cluster block-bootstrap CI**, CUPED, washout. Battery: **A/A CI contains 0 (validation passes)**; rec-only +0.056, static-vs-dynamic +0.078, hybrid +0.103 — detectable **simulated** effects, never a causal lift. 8 tests. `make v1-experiment-dry-run`. See `reports/v1/experiments/V1_EXPERIMENT_REPORT.md`. |
| V1-09 UI, E2E, audit & packaging | TODO | |

## Recommendation track — prerequisite audit (this session)
User chose to **focus on the recommendation system** (V1-07A→D) next.

Environment findings:
- `torch` **MISSING**, `faiss` **MISSING**; `sklearn 1.9.0`, `numpy`, `pandas` present. No internet
  → cannot pip-install torch.
- Data: real `data/raw/citibike/JC-202606-…zip` = **109,897 trips / 106 stations**; deterministic
  `data/fixtures/citibike_sample.csv` (7 trips) for tests; `data/fixtures/gbfs_station_status.json`
  gives capacity/inventory for the demo `HB1xx` stations only (rest → inventory-missing mask).

Resolution:
- User chose "torch 설치 시도" → **installed `torch 2.8.0+cpu`** (this sandbox has internet;
  Python is actually 3.12.10 in `.venv`). Pinned as `pyproject [recsys]` extra.
- **V1-07B/C are now UNBLOCKED**: the full PyTorch dual-encoder + cross-attention reranker path is
  implementable. ExactTorchIndex is the required default; FAISS stays optional (absent).
- Build order: V1-07A (dataset/candidates/baselines/metrics, sklearn) → V1-07B (torch retriever) →
  V1-07C (torch reranker + policy + serving) → V1-07D (incentive/policy simulation).

## Change log
- **V1-00** (this session): created V1 contract package, config, docs, tracking files, and
  `tests/unit/test_v1_contracts.py`. Ran full regression — see counts above.
- **Rec track audit**: recorded torch/faiss blocker; V1-07B/C `BLOCKED_EXTERNAL`.
- **News collection (real)**: `GdeltNewsProvider` now hits GDELT DOC 2.0 (free, key-less) with
  retry/backoff — opt-in (`make v1-collect-news-live`, `ENABLE_GDELT_LIVE=true`), disabled in
  Demo/tests. Proven live: fetched 75 real articles; a tight JC/Hoboken mobility query yields
  ~33 mostly-relevant **June-2026** items (+ keyword noise — honest). Snapshots to a git-ignored
  fixture. Real-news event-lift claim stays `BLOCKED_DATA` until overlap passes the coverage gate.
  See `docs/V1_NEWS_COLLECTION.md`. Experiment Lab UI now shows each test's **A/B definitions**
  (A=대조 policy, B=처리 policy + descriptions).

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
| V1-01 Historical news backfill & coverage gate | TODO | Needs real GDELT → expect `BLOCKED_DATA` for real-news claim; build fixture provider + coverage gate offline. |
| V1-02 Real event extraction & incremental features | TODO | |
| V1-03 Model registry & dual inference | TODO | |
| V1-04 Event-lift evaluation | TODO | Claim gated on V1-01 real news. |
| V1-05 Live news shadow pipeline | TODO | Fixture stream path; live disabled by default. |
| V1-06 Anomaly detection & root cause | TODO | |
| V1-07A Rec contracts/dataset/baselines | **PASSED** | `ml/recsys/*` + `config/recsys.py`. Real run on JC-202606 (109,897 trips → 219,407 samples, test 43,881). Measured B0–B3; **B0 nearest-feasible strongest (HR@1 0.845)** — capacity/MLP don't beat distance (inventory unknown 98%). Honest non-improvement reported in `reports/v1/recsys/V1_RECSYS_BASELINES.md`. 9 leakage/determinism tests. `make evaluate-recommendation`. |
| V1-07B Dual-encoder retriever | TODO | PyTorch; no external pretrained download. |
| V1-07C Cross-attention reranker + policy | TODO | |
| V1-07D Dynamic incentive & simulation | TODO | Simulated only. |
| V1-08 Clustered switchback experimentation | TODO | Simulated/dry-run only. |
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

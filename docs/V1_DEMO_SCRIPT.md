# ShockFlow AI V1 — 2-Minute Demo Script

Fully offline. Start `make api` (127.0.0.1:8000) and `make web` (localhost:3000), then walk the
8-screen console. Every number shown is measured or explicitly labelled simulated.

## Setup (once)

```bash
pip install -e ".[dev,api,ml,recsys,vectorstore]"
make api      # terminal 1
make web      # terminal 2  (cd apps/web && npm install first)
```

## The walk (≈2 min)

1. **자전거 찾기 (rider home)** — set the replay clock to `13:59 · 이벤트 전`: every zone is calm.
   Slide to `15:30 · 콘서트`: event-exposed zones (호보켄/시청/뉴포트) turn 🔴 "곧 부족" with a demand Δ.
   *Alert.*
2. **수요 급증 원인** — pick a hot zone: Article → Event → H3 Zone → Feature trace with grounded
   evidence quotes and the model-attributed Δ (labelled, not causal). *Why.*
3. **뉴스 검색 (FAISS)** — search "PATH suspended Hoboken": semantic ranking over the accumulating
   news vector store; the 3 wire copies of one story are grouped into one same-event cluster.
4. **모델 Lift** — measured B0→B4: history+calendar (M0) beats seasonal naive, but event/graph
   features add **0** (banner: `insufficient_event_overlap`) — with the unlock path shown. *Honest.*
5. **이상 탐지** — 4 detectors flag a stale feed, an impossible capacity, a sudden depletion (root-caused
   to a source event with article evidence), and a forecast residual — all flagged synthetic.
6. **시나리오 비교** — toggle an event off and compare the counterfactual forecast. *Simulate.*
7. **재배치 계획** — MILP produces a feasible relocation plan (shortage 8→0). *Act.*
8. **실험 랩** — clustered-switchback battery: A/A passes (CI contains 0), then A(대조)=무행동 vs
   B(처리)=하이브리드 shows a **simulated** ITT — never a causal lift.

## One-shot checks (no UI)

```bash
make test                     # 199 passed, 1 skipped
pytest tests/e2e/test_v1_golden_path.py   # offline golden path across all endpoints
make rebalance-demo           # MILP == enumeration optimum + QUBO validation
make v1-evaluate-anomalies    # detectors on the synthetic-fault scenario
make v1-experiment-dry-run    # A/A + policy switchback (simulated)
make v1-news-vectorstore      # FAISS semantic search + clustering
```

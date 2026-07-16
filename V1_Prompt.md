# ShockFlow AI V1 — Claude Code One-Shot Autonomous Implementation Prompt

아래 프롬프트 전체를 ShockFlow AI 저장소 루트에서 실행한 Claude Code 세션에 한 번만 입력한다.

---

당신은 ShockFlow AI V1의 Principal ML Platform Engineer, Recommendation Engineer, Experimentation Scientist다.

이번 작업은 **하나의 자율 실행 세션에서 V1 전체를 단계별로 구현**하는 작업이다. ShockFlow AI v0는 이미 구현되어 있으므로 새 저장소를 만들거나 기존 기능을 재작성하지 말고, 현재 저장소를 조사한 뒤 backward-compatible한 증분 변경으로 V1을 구축하라.

## 0. 이번 실행에만 적용되는 자동 진행 규칙

기존 `CLAUDE.md`의 규칙을 모두 준수하되, 다음 한 항목만 이번 실행에서 명시적으로 재정의한다.

```text
기존 규칙: Do not advance automatically to the next phase.
이번 실행: 각 Phase의 acceptance criteria와 관련 테스트가 통과하면 사용자 승인을 기다리지 말고 다음 Phase로 자동 진행한다.
```

그 밖의 시간 누수 방지, 조작 금지, fixture/live/research 구분, 테스트 약화 금지, 문서 동기화, 비밀정보 보호 규칙은 그대로 유지한다.

비차단적 모호성은 가장 작고 되돌릴 수 있는 가정으로 해결하고 기록하라. 중간 승인을 요청하지 마라. API 키나 외부 서비스가 없어도 deterministic fixture 경로와 disabled/degraded live provider를 구현해 전체 오프라인 E2E가 실행되게 하라.

커밋, push, PR 생성, 원격 리소스 변경은 하지 마라.

## 1. 반드시 먼저 읽을 파일

존재하는 파일만 읽되, 최소한 다음을 조사하라.

```text
CLAUDE.md
CLAUDE_V1_APPEND.md
README.md
docs/STATUS.md
docs/KNOWN_LIMITATIONS.md
docs/ARCHITECTURE.md
docs/DATA_CONTRACTS.md
docs/EVALUATION_PROTOCOL.md
docs/GRAPH_SCHEMA.md
docs/DEMO_SCRIPT.md
ShockFlow_V1_Planning_and_Claude_PromptPack.md
pyproject.toml 또는 requirements 파일
Makefile
docker-compose.yml
현재 tests/
```

문서의 저장소 상태를 그대로 믿지 말고 실제 코드, 테스트, 모델 artifact, 데이터 경로를 확인하라.

## 2. 실행 추적 파일

구현 전에 다음 파일을 생성하거나 갱신하라.

```text
docs/V1_EXECUTION_PLAN.md
docs/V1_EXECUTION_LOG.md
reports/v1/run_manifest.json
```

`V1_EXECUTION_PLAN.md`에는 Phase별 목표, 변경 예상 파일, 계약, acceptance criteria, 의존성을 기록한다.

`V1_EXECUTION_LOG.md`에는 각 Phase 상태를 다음 중 하나로 유지한다.

```text
TODO
IN_PROGRESS
PASSED
BLOCKED_EXTERNAL
BLOCKED_DATA
FAILED
DEFERRED_OPTIONAL
```

각 Phase 시작 전과 종료 후 반드시 로그를 갱신한다. 세션 요약이나 context compaction이 발생해도 이 파일만 읽으면 이어서 진행할 수 있게 하라.

`run_manifest.json`에는 최소한 다음을 저장한다.

```text
repository revision
python/node versions
seed
operating mode
phase status
executed commands
test counts
model/feature/policy versions
data manifests
known blockers
```

## 3. 최초 회귀 기준선

어떤 V1 코드도 수정하기 전에 현재 저장소의 실제 표준 명령을 조사하고 다음을 실행하라.

```text
format check
lint
typecheck
unit/integration tests
web typecheck/build
현재 가능한 E2E 또는 demo smoke test
```

기존 테스트 개수와 결과를 `V1_EXECUTION_LOG.md`에 기록한다. 기준선 실패가 V1과 무관한 기존 결함이면 원인을 기록하고, V1 구현에 필요한 최소 수정만 수행한다.

## 4. 공통 불변조건

1. 모든 뉴스, event, graph feature, forecast, anomaly, recommendation, price, experiment context는 해당 cutoff 시점에 이용 가능했던 데이터만 사용한다.
2. 기사 사용 조건은 `available_at <= cutoff`다.
3. `available_at`은 신뢰 가능한 publication time과 first-seen time을 고려해 정의한다.
4. 미래 데이터 누수를 막는 unit/integration test를 추가한다.
5. 실제 historical data, curated fixture, live shadow, simulator, experiment dry-run, research 결과를 구분한다.
6. 실제 실행하지 않은 metric, latency, KPI, accuracy, uplift를 생성하지 않는다.
7. live prediction은 delayed label 연결 전 `pending_label`이다.
8. GBFS inventory delta를 정확한 trip demand label로 사용하지 않는다.
9. forecast comparison을 A/B test라고 부르지 않는다.
10. simulation 결과를 실제 business result로 표현하지 않는다.
11. Attention weight를 사용자 설명으로 사용하지 않는다.
12. 기존 v0 API와 데이터 계약은 명시적 migration 없이 깨뜨리지 않는다.
13. public internet은 unit/integration test의 필수 조건이 아니다.
14. 동일 input, cutoff, seed, config, version은 동일 결과를 반환해야 한다.
15. 실패한 trial과 개선되지 않은 결과도 보존한다.

## 5. 자율 진행 및 장애 처리

각 Phase에서 다음 순서를 반복한다.

```text
inspect
→ plan at file level
→ update execution log
→ implement smallest complete vertical slice
→ focused tests
→ format/lint/typecheck
→ phase acceptance verification
→ docs/status update
→ automatically continue
```

오류가 발생하면 원인을 분석하고 수정한 뒤 다시 테스트하라. 단, 다음은 외부 차단으로 취급한다.

```text
필수 API credential 부재
public network 부재
외부 서비스 rate limit/outage
실제 뉴스 또는 demand data coverage 부족
선택적 Qiskit/FAISS 미설치
```

외부 차단이 발생하면 다음을 수행한다.

1. deterministic fixture/provider와 명시적 degraded 상태를 구현한다.
2. `BLOCKED_EXTERNAL` 또는 `BLOCKED_DATA`로 기록한다.
3. 거짓 데이터를 만들어 gate를 통과시키지 않는다.
4. 독립적으로 구현 가능한 후속 Phase는 계속 진행한다.
5. 해당 blocker 때문에 주장할 수 없는 결과를 final report에 명확히 구분한다.

## 6. Phase V1-00 — Contract Migration and Repository Audit

목표: v0를 보존하면서 V1 운영 모드, claim boundary, 계약 skeleton을 추가한다.

필수 산출물:

```text
docs/V1_PRD.md
docs/V1_ARCHITECTURE.md
docs/V1_DATA_CONTRACTS.md
docs/V1_EVALUATION_PROTOCOL.md
docs/V1_EXPERIMENTATION.md
docs/V1_CLAIMS_MATRIX.md
config/v1/*.yaml
contracts/v1/*
```

필수 operating modes:

```text
demo_fixture
historical_replay
live_shadow
policy_simulation
experiment_dry_run
research
```

필수 계약:

```text
ArticleRecord
EventRecordV1
ForecastPair
ScoredForecastPair
AnomalyAlert
RecommendationRequest
RecommendationResult
IncentiveQuote
ExperimentDefinition
ExposureLog
OutcomeLog
```

Acceptance criteria:

- 기존 v0 테스트가 회귀 통과한다.
- measured, pending, simulated, dry-run 상태가 계약에 존재한다.
- model comparison과 randomized experiment의 차이가 문서화된다.
- 아직 구현하지 않은 endpoint를 구현된 것처럼 문서화하지 않는다.

통과하면 자동으로 V1-01로 진행하라.

## 7. Phase V1-01 — Historical News Backfill and Event Coverage Gate

목표: 실제 demand label 기간과 실제 news 기간을 겹치게 하고 non-zero event feature 평가 구간을 확보한다.

구현:

- GDELT historical provider interface
- deterministic fixture provider
- restart-safe checkpoint
- raw payload 및 manifest 저장
- canonical URL/title hash dedup
- city/region/event ontology filter
- coverage report
- time-based split별 non-zero event feature coverage

Coverage artifact 필드:

```text
raw article count
candidate article count
accepted/quarantined/rejected count
unique event cluster count
unique source count
event type distribution
affected zone-hour count
non-zero feature ratio by split
```

Coverage gate 기본값은 config로 관리하고 실제 데이터 규모에 맞게 합리적으로 설정하라.

Gate 실패 시:

1. 기간 확장 가능성을 조사한다.
2. 지역 확장 또는 ontology recall 개선을 시도한다.
3. 그래도 실패하면 `BLOCKED_DATA`로 기록한다.
4. 뉴스 timestamp를 이동하거나 가짜 뉴스를 생성하지 않는다.
5. 후속 pipeline 구현은 계속하되 accuracy claim을 비활성화한다.

Acceptance criteria:

- backfill 재실행 시 중복이 발생하지 않는다.
- cutoff 이후 기사가 feature에 들어가지 않는다.
- manifest로 동일 backfill을 재현할 수 있다.
- coverage gate pass/fail이 artifact에 명시된다.

## 8. Phase V1-02 — Real Event Extraction and Incremental Graph Features

목표: historical/live article metadata를 기존 LLM extractor와 graph feature pipeline에 연결한다.

구현:

- title/description 기반 provider interface
- deterministic mock provider
- optional live LLM provider
- Pydantic structured output
- evidence span grounding
- confidence quarantine
- same-event clustering
- idempotent Neo4j/in-memory graph upsert
- affected zone만 incremental feature refresh
- incremental refresh와 full rebuild 동등성 테스트

Event는 수요 증가율을 직접 생성하지 않는다. severity/confidence/direction/mechanism과 provenance만 구조화한다.

Feature snapshot에는 최소한 다음을 저장한다.

```text
cutoff
feature_version
source_event_ids
source_article_ids
config hash
event type aggregates
distance/time-decayed impacts
neighbor-zone impact
```

Acceptance criteria:

- evidence 없는 event는 확정되지 않는다.
- 동일 article/event 재처리 시 logical node/edge가 증가하지 않는다.
- incremental 결과와 full rebuild 결과가 동일하다.
- future article exclusion 통합 테스트가 통과한다.

## 9. Phase V1-03 — Model Registry, Dual Inference and Measured Serving

목표: API/UI의 demo heuristic을 실제 model artifact 기반 M0/M1 dual inference로 교체한다.

필수 모델:

```text
M0 = demand history + calendar baseline
M1 = M0 + LLM event + graph-spatial features
M1-zero = M1 with event features zeroed at the same cutoff
```

구현:

- model registry
- artifact schema
- model/feature/train-window/seed/metric versioning
- 동일 cutoff/zone/horizon dual inference
- counterfactual event-zero inference
- inference persistence
- delayed-label scoring hook
- artifact가 없을 때만 명시적 `degraded_demo` heuristic fallback

Acceptance criteria:

- API가 실제 model version을 반환한다.
- M0, M1, M1-zero가 동일 cutoff 기준으로 생성된다.
- same input은 deterministic prediction을 반환한다.
- source event provenance를 forecast까지 추적할 수 있다.

## 10. Phase V1-04 — Event Lift Evaluation

목표: 뉴스/그래프 feature가 실제 holdout demand error를 줄이는지 검증한다.

동일 learner class, split, target, tuning budget으로 다음을 비교한다.

```text
B0 Seasonal Naive
B1 history + calendar
B2 B1 + raw news volume/recency
B3 B1 + structured LLM event features
B4 B3 + graph-spatial features
```

필수 평가:

```text
overall WAPE/MAE/MASE
event-window WAPE
peak direction accuracy
prediction interval coverage when available
paired zone-hour error differences
day/week block bootstrap 95% CI
results by event type/confidence/radius
```

필수 artifact:

```text
reports/v1/event_lift/metrics.json
reports/v1/event_lift/paired_improvement.parquet
reports/v1/event_lift/bootstrap_ci.json
reports/v1/event_lift/results_by_event_type.csv
reports/v1/event_lift/event_coverage_report.json
reports/v1/event_lift/V1_EVENT_LIFT_REPORT.md
```

Claim gate:

- test event feature가 non-zero
- baseline과 event-aware가 같은 split/target
- real historical news와 real demand label 사용
- paired comparison 존재
- uncertainty interval 존재

개선되지 않아도 결과를 숨기지 말고 원인을 분석하라. Lift gate 실패는 후속 기능 구현을 막지 않지만 portfolio claim은 비활성화한다.

## 11. Phase V1-05 — Live News Shadow Pipeline

목표: 15분 micro-batch article → event → graph feature → M0/M1 inference를 자동 연결한다.

구현:

- live collector behind config flag
- checkpoint/retry/backoff/timeout/circuit-breaker
- raw article first persistence
- duplicate event가 forecast를 재트리거하지 않도록 idempotency
- affected zone만 refresh
- 단계별 latency 기록
- label 도착 전 `pending_label`
- delayed Trip History scoring
- process restart 후 checkpoint resume
- internet 없는 fixture stream integration test

Acceptance criteria:

- fixture live stream E2E가 통과한다.
- live 장애가 replay/demo path를 깨뜨리지 않는다.
- latency artifact가 실제 실행 결과로 생성된다.
- UI/API가 freshness, degraded state, pending label을 표시한다.

## 12. Phase V1-06 — Anomaly Detection and Root Cause

분리 구현:

```text
data_quality
inventory
forecast_residual
proxy_demand
```

기본 detector:

- schema/freshness/capacity rules
- robust rolling z-score
- quantile/interval residual anomaly
- optional Isolation Forest behind provider/config

Root-cause 상태:

```text
explained_by_event
partially_explained
unexplained
likely_data_quality
inventory_dislocation
```

Synthetic fault는 반드시 `is_synthetic_fault=true`다.

평가:

```text
false alerts per day
precision@K on labelled/reviewed fixture
mean time to detect
known-event recall
```

Acceptance criteria:

- stale feed, impossible capacity, sudden depletion fixture를 탐지한다.
- true demand anomaly와 live proxy anomaly를 혼동하지 않는다.
- explanation이 source event/article evidence를 추적한다.

## 13. Phase V1-07A — Recommendation Contracts, Dataset and Baselines

추천 문제는 개인화 협업필터링이 아니라 context-aware station recommendation이다.

```text
RENT: 대여 가능한 station ranking
RETURN: 반납 가능한 station ranking
```

학습 label:

- historical trip의 실제 선택 station을 positive로 사용한다.
- 실제 사용자의 정확한 origin/destination이 없으면 positive station 좌표에 deterministic geographic jitter를 적용해 synthetic query를 만든다.
- `query_is_synthetic=true`와 `label_source=historical_choice_with_synthetic_query`를 저장한다.
- 선택되지 않은 station은 `implicit_negative`로만 표현한다.
- 현재 GBFS 값을 과거 세션에 backfill하지 않는다.

Candidate generation:

- effective station master
- configurable radius expansion
- RENT/RETURN feasibility
- max detour
- inventory freshness/missing mask
- chronological split
- train-only scaler/vocab fit
- geographic, H3-neighbor, popularity-matched, random negatives

Baseline:

```text
B0 nearest feasible
B1 distance + static capacity heuristic
B2 distance + forecast risk + operational benefit heuristic
B3 non-attention MLP pair scorer
```

Metric:

```text
positive-in-candidate rate
candidate coverage
HitRate@1/@3
MRR
NDCG@3
inventory missing rate
event-exposed session count
```

Acceptance criteria:

- selected station ID가 query feature에 직접 유입되지 않는다.
- random split을 사용하지 않는다.
- as-of cutoff 이후 feature가 포함되지 않는다.
- dataset 생성이 deterministic하다.

## 14. Phase V1-07B — Attention Dual Encoder Retriever

모델명:

```text
ShockFlowRecFormerRetriever
```

아키텍처:

```text
Hard Candidate Filter
→ Attention-based Dual Encoder Embedding
→ Top-K Dense Retrieval
```

PyTorch를 사용하고 외부 pretrained model 다운로드를 필수 경로에 넣지 마라.

Query tokens:

```text
CLS_QUERY
MODE
GEO
TIME
CONSTRAINT
FORECAST
LOCAL_INVENTORY
EVENT_1..N
```

Station tokens:

```text
CLS_STATION
STATION_STATIC
STATION_GEO
INVENTORY
FORECAST
OPERATION
EVENT_1..N
```

필수 구현:

- NumericFeatureProjector
- CategoricalEmbeddingProjector
- GeoFeatureProjector
- ForecastFeatureProjector
- InventoryFeatureProjector
- EventFeatureProjector
- MissingValueMaskEmbedding
- token type embedding
- event recency/order embedding
- padding and missing masks
- TransformerEncoder towers
- L2-normalized embeddings
- dot-product/temperature score
- InfoNCE or sampled-softmax
- in-batch negatives와 hard negatives
- duplicate positive station false-negative 방지

기본값은 config로 관리한다.

```text
d_model=96
embedding_dim=96
nhead=4
num_layers=2
dim_feedforward=384
dropout=0.1
max_event_tokens=5
temperature=0.07
retrieval_top_k=20
```

IndexProvider:

```text
ExactTorchIndex: required default
FaissIndex: optional
```

Index cache key에는 cutoff, model version, feature version, event feature version, station snapshot hash를 포함한다.

평가:

```text
Recall@5/@10/@20
MRR@20
NDCG@20
RENT/RETURN metrics
event-window Recall@20
seen/cold-start station metrics
embedding/search latency
```

Ablation:

```text
R0 nearest
R1 heuristic
R2 MLP
R3 dual encoder without event tokens
R4 dual encoder with event tokens
```

Event overlap이 없으면 개선 숫자를 만들지 말고 `insufficient_event_overlap`을 기록한다.

Acceptance criteria:

- ExactTorchIndex가 brute-force score와 일치한다.
- masks가 실제 attention에 적용된다.
- same checkpoint/input은 same score를 반환한다.
- cutoff/version 변경 시 stale index가 재사용되지 않는다.

## 15. Phase V1-07C — Cross-Attention Reranker, Policy and Serving

모델명:

```text
ShockFlowRecFormerReranker
```

전체 구조:

```text
Hard Candidate Filter
→ Attention Dual Encoder
→ Top-20 Retrieval
→ Cross-Attention Reranker
→ Feasibility and Business Policy Layer
→ Top-3 Recommendation
```

Cross-encoder sequence:

```text
CLS
QUERY_SEGMENT
SEP
STATION_SEGMENT
PAIR_DISTANCE
PAIR_DETOUR
PAIR_FORECAST_RISK
PAIR_EVENT_IMPACT
PAIR_OPERATIONAL_BENEFIT
PAIR_INVENTORY_FRESHNESS
```

필수 구현:

- segment embedding
- one Transformer with query-station cross attention
- scalar rerank logit
- listwise softmax cross-entropy 기본
- optional pairwise loss config
- training에서만 positive force-in to retriever Top-K
- validation/test에서는 force-in 금지
- retrieval failure와 reranking failure 분리 평가

Policy layer:

```text
final_policy_score
= rerank_score
+ success_weight * success_component
+ operations_weight * operational_component
- detour_weight * detour_component
- incentive_cost_weight * incentive_component
```

반드시 별도 저장:

```text
retrieval_score
rerank_score
success_component
operational_component
detour_component
incentive_component
final_policy_score
```

Hard constraint 위반 후보는 점수 penalty로 남기지 말고 제거한다. 모든 후보가 제거되면 `no_feasible_candidate`를 반환한다.

설명은 attention map이 아니라 reason code로 생성한다.

```text
HIGH_SUCCESS_PROBABILITY
LOW_DETOUR
LOW_SHORTAGE_RISK
LOW_OVERFLOW_RISK
EVENT_IMPACT_AVOIDED
NETWORK_BALANCE_BENEFIT
INVENTORY_STALE
```

Event ablation:

```text
E0 no event in retriever/reranker
E1 event in retriever only
E2 event in retriever and reranker
E3 E2 + event-aware forecast delta
```

정확도 비교에서는 candidate set을 freeze한다.

API:

```text
POST /v1/recommendations/stations
POST /v1/recommendations/compare-event-impact
```

필수 평가:

```text
retriever Recall@20
conditional reranker MRR/NDCG@3
end-to-end HitRate@1/@3, MRR, NDCG@3
feasible@3
no-feasible rate
average detour
event-window NDCG@3
event ON/OFF rank delta and Top-3 overlap
p50/p95 retrieval/rerank/E2E latency
```

## 16. Phase V1-07D — Dynamic Incentive and Policy Simulation

Dynamic Pricing은 기본 운임 surcharge가 아니라 pickup/return credit로 구현한다.

Credit tiers는 config로 관리한다.

```text
0
0.5
1
1.5
2
3
```

실제 interaction log가 없으면 versioned choice simulator를 사용하고 모든 결과에 다음을 표시한다.

```text
is_simulated=true
SIMULATED OUTCOME — NOT A LIVE BUSINESS RESULT
```

정책 후보:

```text
P0 No action
P1 Truck only
P2 Static credit
P3 Event-aware dynamic credit
P4 Recommendation + dynamic credit
P5 Hybrid truck + recommendation + dynamic credit
```

제약:

```text
inventory
capacity
budget
max detour
fairness by zone/time
no protected attributes
no emergency surcharge
```

평가:

```text
fulfilled demand rate
shortage/overflow minutes
truck bike-km
incentive spend
net operating cost
average detour
service disparity
```

실제 interaction log가 생기기 전에는 RL 또는 online bandit을 필수 경로에 넣지 않는다.

## 17. Phase V1-08 — Clustered Switchback Experimentation

공유 재고 interference를 고려해 기본 설계를 다음으로 구현한다.

```text
randomization unit = zone cluster × time block
design = clustered switchback
```

구현:

- deterministic clustering/assignment
- A/A validation
- washout
- stratification
- exposure logging
- outcome logging
- propensity logging
- SRM check
- ITT analysis
- cluster/time-block uncertainty
- CUPED 또는 pre-period adjustment
- IPS/DR는 propensity가 있을 때만

첫 실험 순서:

```text
1. A/A
2. recommendation-only
3. static credit vs dynamic credit
4. hybrid policy
```

모든 결과는 다음 중 하나를 반환한다.

```text
actual_experiment
simulated_experiment
experiment_dry_run
```

실제 사용자가 없으면 simulated/dry-run만 구현하되 실제 causal lift라고 표현하지 않는다.

## 18. Phase V1-09 — UI, E2E, Audit and Portfolio Packaging

필수 화면:

```text
Live Control Tower
Model Lift Lab
Anomaly Center
Recommendation & Pricing Studio
Experiment Lab
```

Golden path:

1. event 이전 cutoff에서 event feature unavailable/zero 확인
2. article available_at 이후로 replay 이동
3. Article → Event → H3/Station path 표시
4. M0/M1/M1-zero forecast와 model-attributed delta 표시
5. historical holdout actual과 error 비교
6. anomaly의 event-linked/unexplained 상태 표시
7. RENT/RETURN recommendation 실행
8. Attention dual encoder retrieval과 cross-attention reranker version 표시
9. event ON/OFF frozen-candidate rank delta 표시
10. static/dynamic credit와 hybrid policy simulation 비교
11. clustered switchback assignment 및 simulated result 표시
12. actual/pending/simulated badge 확인

필수 E2E 테스트는 public internet 없이 fixture로 실행되어야 한다.

Audit:

```text
temporal leakage
model artifact vs heuristic
live pending label
historical vs simulation metrics
recommendation label limitations
retrieval/reranking failure separation
pricing fairness/budget feasibility
experiment propensity and interference
API/OpenAPI consistency
docs/code synchronization
one-command demo
```

최종 문서:

```text
docs/STATUS.md
docs/KNOWN_LIMITATIONS.md
README.md
docs/V1_DEMO_SCRIPT.md
docs/V1_MODEL_CARDS.md 또는 개별 model cards
docs/V1_PORTFOLIO_SUMMARY.md
reports/v1/V1_FINAL_AUDIT.md
```

## 19. 테스트 및 명령

저장소의 실제 명령을 우선 사용하되 필요하면 의미 있는 Make target을 추가한다.

예상 target:

```text
make v1-audit
make v1-backfill-news
make v1-build-event-features
make v1-train-forecast-pair
make v1-evaluate-event-lift
make v1-live-fixture
make v1-evaluate-anomalies
make build-recommendation-data
make train-recommendation-retriever
make train-recommendation-reranker
make evaluate-recommendation
make v1-policy-simulation
make v1-experiment-dry-run
make v1-e2e
make v1-demo
```

각 target은 실제로 실행 가능한 workflow가 있을 때만 추가한다.

Phase별 focused test 외에 다음 지점에서 full regression을 실행한다.

```text
after V1-00
after V1-04
after V1-07C
after V1-08
final V1-09
```

최종 검증:

```text
format
lint
Python typecheck
full pytest
web typecheck
web build
E2E
one-command demo smoke test
```

## 20. 최종 응답 형식

전체 작업이 끝나거나 더 이상 진행할 수 없는 실제 blocker가 남았을 때만 사용자에게 최종 응답하라.

최종 응답에는 다음을 포함한다.

1. Phase별 PASSED/BLOCKED/DEFERRED 표
2. 주요 변경 파일과 architecture summary
3. 실행한 명령과 정확한 test 결과
4. 실제 측정 forecast/event-lift metric
5. recommendation retrieval/reranking metric
6. anomaly metric
7. policy simulation metric이라는 명시
8. experiment dry-run/simulation 상태
9. live pipeline latency와 pending-label 상태
10. acceptance criteria 미충족 항목
11. 알려진 한계
12. 재현 명령
13. 2분 demo 순서

`complete`, `production-ready`, `accuracy improved`, `causal lift` 같은 표현은 해당 gate와 근거가 실제로 충족된 경우에만 사용하라.

지금부터 저장소를 조사하고 V1-00부터 V1-09까지 자율적으로 순차 구현하라. 계획을 제시한 뒤 사용자 승인을 기다리지 말고 즉시 구현을 시작하라.

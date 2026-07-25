# ShockFlow AI — V2 기획을 위한 핸드오프 보고서

이 문서는 **GPT에게 V2 초안 작성을 의뢰**하기 위한 현황 보고서입니다. 지금까지(v0 + V1)의 실제
구현 상태, 측정된 결과, 결과 표기 경계, 데이터 수집 현황, 남은 갭, V2 후보 방향을 한 곳에 정리합니다.
모든 수치는 실행/테스트로 뒷받침되며, 측정 불가한 것은 명시적으로 disabled/blocked 표기했습니다.

---

## 1. 프로젝트 한 줄 정의

이벤트를 인지하는 도시 자전거(Citi Bike, 저지시티/호보켄) **시간대·H3 zone 단위 수요 예측 +
차량 재배치·추천·인센티브 의사결정 지원** 시스템. 핵심 규율은 **결과 표기**: 모든 값이
`measured / pending / simulated / blocked` 중 하나로 라벨링되며, 인과(causal)·양자우위 주장은 하지 않음.

- 스택: Python 3.12(FastAPI, pydantic v2, scikit-learn, **PyTorch CPU**, **FAISS**, h3, scipy),
  Next.js 15(App Router, TS strict), 오프라인 fixture로 완전 재현.
- 코드: `contracts/`(+`v1/`), `pipelines/`(collectors·events·features·graph·**live**),
  `ml/`(forecasting·recsys·pricing·experiment·anomaly·**vectorstore**), `optimization/`,
  `services/api/`, `apps/web/`. 테스트 **200 passed, 1 skipped**.

## 2. 데이터 흐름 (실제 구현)

```text
뉴스(fixture | GDELT 실시간) ──> 백필+커버리지 게이트 ──> LLM 이벤트 추출
  ──> 이벤트 그래프(idempotent) ──> as-of 그래프 피처(증분 == 전체 재빌드)
  ──> FAISS 뉴스 벡터스토어(누적·의미검색·같은사건 클러스터)
  ──> M0/M1/M1-zero 예측(측정 B0–B4) ──> 이벤트 lift 게이트
  ──> 추천(듀얼인코더 retrieve → cross-attn rerank → 정책) ──> 동적 인센티브 시뮬
  ──> 클러스터드 스위치백 실험 ──> 이상탐지+근본원인 ──> 라이브 섀도(pending)
  ──> 8화면 웹 콘솔
```

## 3. 측정된 결과 (실데이터 JC-202606 = 109,897 trips)

| 영역 | 측정값 | 비고 |
|---|---|---|
| 예측 M0(과거+달력) | WAPE **0.516** (B0 계절naive 0.658) | 큰 개선 |
| 예측 M1(이벤트+그래프) | WAPE 0.516 = **M0와 동일** | 이벤트 미중첩 → lift 0 |
| 추천 retriever | Recall@20 **0.952**, MRR@20 0.582 | 오픈 리트리벌 |
| 추천 E2E | HitRate@3 **0.754**, feasible@3 **1.00**, p50 16ms | reranker+정책 |
| 재배치 | MILP == enumeration 최적, greedy always feasible | |
| 실험 A/A | CI가 0 포함(설계 검증) | 처리효과는 simulated |
| 이상탐지 | 4탐지기, clean 데이터 **오탐 0**, 급감→이벤트 근거연결 | |

## 4. 결과 표기 경계 (V2에서 반드시 유지)

| 표면 | claim 상태 | 이유 |
|---|---|---|
| 예측 ablation(B0–B4) | **measured** | 실 홀드아웃 |
| **이벤트 lift** | `insufficient_event_overlap` (비활성) | 큐레이션 이벤트(7/12)가 6월 평가창 이후 → 피처 0 |
| 실뉴스 커버리지 | `BLOCKED_DATA` | 실 백필이 게이트 통과해야 |
| 라이브 섀도 예측 | `pending` | 지연 라벨 도착 전 |
| 추천/인센티브/실험 | `simulated` | 실사용자 없음 → 인과 lift 아님 |
| QUBO/QAOA | research-only | 시뮬레이터, 우위주장 없음 |

## 5. 뉴스 데이터 수집 현황 (중요)

- **수집 방법 완성·검증됨**: GDELT DOC 2.0(무료·키불필요) 실연동, `make v1-collect-news-live`
  (opt-in). 자전거 중심 쿼리로 조정: `Citi Bike / bike share / bike lane / bicycle / cycling /
  e-bike + NJ Transit / PATH / commute / 도로폐쇄 / concert / festival / flood`, JC/Hoboken 앵커.
- **실수집 데이터 누적**: 실제 **2026년 6월(6/11–7/5) 33건**을 FAISS 벡터스토어에 누적(의미검색·
  같은사건 클러스터 동작 확인). 수요 데이터(6월)와 시기가 겹침.
- **제약**: 이 샌드박스의 **공유 IP가 GDELT rate-limit(429)에 걸려** 대량(수백 건) 수집은
  현재 불가. 사용자의 개인 환경/IP에서는 정상 수집됨(주별 창으로 나눠 `--start/--end` 지정 권장).
- **가짜 뉴스는 만들지 않음**(invariant). 부족분은 실제 수집으로만 채움.

## 6. 남은 유일한 "실측" 갭 → V2의 1순위 후보

**이벤트가 수요 예측을 실제로 개선하는가**를 측정하려면:
1. 6월(평가창과 겹치는) 뉴스를 **충분히** 수집 (GDELT, 개인 IP) → FAISS 누적
2. 이벤트 추출 → as-of 그래프 피처가 6월 평가창에서 **비영(0 아님)**이 되도록
3. M1 재학습 → V1-04 게이트(paired B4−B1 + block-bootstrap CI) 재실행
4. 통과 시 이벤트 lift를 **measured**로 승격, Model Lift Lab에 실수치 노출

이것이 유일하게 "insufficient_event_overlap → measured" 전환을 여는 경로입니다.

## 7. V2 후보 방향 (GPT가 초안 잡을 범위 옵션)

- **A. 실 이벤트 lift 확보** — §6 파이프라인 완주(실뉴스 대량 수집→재학습→게이트 통과). 가장 임팩트 큼.
- **B. 신경망 임베더** — 벡터스토어의 lexical char-hash를 문장 임베더로 교체(오프라인 가능한 소형
  모델), 같은사건 클러스터·의미검색 품질↑, 추천 텍스트 피처화.
- **C. 추천 고도화** — 실 사용자 로그 확보 전제의 온라인 학습/뱅딧은 금지 유지; frozen-candidate
  이벤트 ablation(E0–E3) 실측, cold-start 개선.
- **D. 라이브화** — 라이브 섀도 → 실제 서빙(A/B 스위치백 실집행), pending→measured 라벨 연결.
- **E. 확장 데이터** — 날씨/MTA/permitted-events collector 추가(모두 flag 뒤, Demo 오프라인 불변).
- **F. 운영 지표** — 이상탐지 precision@K·MTTD를 라벨 fixture로 실측, 알림 파이프라인화.

**V2에서도 지켜야 할 불변**: 시간 누수 방지(as-of), 가짜 수치·뉴스 금지, fixture/live/research 구분,
simulated≠business result, 인과·양자우위 주장 금지, v0/V1 계약 backward-compat.

## 8. 재현 명령

```bash
make install && make test          # 200 passed, 1 skipped
make api && make web               # 8화면 콘솔 (127.0.0.1:8000 / localhost:3000)
pytest tests/e2e/test_v1_golden_path.py   # 오프라인 골든패스 E2E
make v1-collect-news-live          # (개인 IP) 실 GDELT 자전거 뉴스 수집 → FAISS 누적
make v1-news-vectorstore           # 벡터 의미검색 + 같은사건 클러스터
make v1-evaluate-anomalies / v1-experiment-dry-run / v1-live-fixture
```

세부: `reports/v1/V1_FINAL_AUDIT.md`, `docs/V1_PORTFOLIO_SUMMARY.md`,
`docs/V1_EXECUTION_LOG.md`, `docs/V1_NEWS_COLLECTION.md`.

---

### GPT에게 (V2 초안 요청 시 프레이밍)

> 위 현황을 전제로, **§7의 방향 중 하나 이상을 골라 V2 실행 프롬프트/계획을 초안**해 주세요.
> 반드시 §4·§7 말미의 결과 표기 불변을 유지하고, 각 단계에 **acceptance criteria + 측정 artifact +
> 재현 명령**을 포함하세요. 가장 임팩트 큰 시작점은 §6(실 이벤트 lift 확보)입니다.

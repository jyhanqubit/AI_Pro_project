# ShockFlow AI

이벤트를 인지하는 도시 모빌리티 수요 예측 및 차량 재배치 의사결정 지원 시스템.

ShockFlow AI는 시간 정보가 붙은 이벤트에서 불규칙한 수요 충격을 감지해 추적 가능한 graph feature로 바꿉니다.
이 feature가 예측에 준 **모델 기여**(model-attributed) 영향(입증된 인과는 아닙니다)을 정량화한 뒤, 그 결과를
실제 운영에 쓸 수 있는 재배치 조치로 이어줍니다.

```text
Citi Bike 수요 이력
+ 시간 정보가 붙은 뉴스 / 이벤트 입력
+ 현재 station 재고
→ LLM 이벤트 추출 → Neo4j 이벤트 graph → as-of numeric graph feature
→ H3 Zone-시간 수요 예측 → 설명 및 시나리오 비교 → 실행 가능한 재배치 계획
```

개발 전반의 운영 계약은 [CLAUDE.md](CLAUDE.md)에 정리해 두었습니다.

## 운영 모드

모든 레코드와 응답, 화면은 자신의 모드를 명시합니다. `demo_fixture`, `historical_replay`,
`live`, `research` 중 하나입니다. **Demo Mode는 외부 API 키 없이 완전히 오프라인으로 돌아갑니다.**

## 시작하기

```bash
make install       # .venv 생성 + 패키지(editable)와 dev 도구 설치
make lint          # ruff check + format check
make typecheck     # mypy
make test          # pytest
make collect-demo    # 세 개의 fixture collector를 오프라인으로 돌리고 요약 출력
make build-features  # 수요 집계(H3 Zone x 로컬 시간) + 누수 방지 feature
make extract-events-demo  # 뉴스 fixture에서 이벤트 추출 (결정적 mock LLM)
make graph-upsert-demo    # 추출한 이벤트를 오프라인 event graph에 업서트 (idempotent)
make graph-features-demo  # 여러 cutoff에서 as-of graph feature 생성 (누수 방지)
make rebalance-demo       # 골든패스 재배치 계획 (greedy / MILP / exact / QUBO 검증), 오프라인
make api                  # 오프라인 replay API (127.0.0.1:8000, Demo Mode, 키 불필요)
make web                  # Next.js 운영자 UI (apps/web; 먼저 npm install 필요)
```

> 윈도우에서 `make`를 쓸 수 없다면 위 명령에 대응하는 명령을 직접 실행하세요. 예를 들면
> `python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"` 처럼요.

실행 전에 `.env.example`을 `.env`로 복사하세요. 기본값은 안전하고 오프라인에서도 문제없이 동작합니다.

## 저장소 구조

| 경로 | 용도 |
|------|------|
| `contracts/` | 경계 전반에서 공유하는 타입 지정 Pydantic v2 data contract (§6) |
| `services/api/` | FastAPI 서비스 (Phase 07) |
| `pipelines/collectors/` | 데이터 collector: Citi Bike, 뉴스 fixture, GBFS |
| `pipelines/events/` | LLM 이벤트 추출 |
| `pipelines/features/` | 수요 집계(H3 Zone x 로컬 시간) + 누수 방지 feature |
| `ml/forecasting/` | baseline 및 이벤트 인지 예측 모델 |
| `optimization/classical/` | Greedy / MILP 재배치 |
| `optimization/quantum/` | QUBO / QAOA 리서치 모드 |
| `apps/web/` | Next.js 운영자 UI (Phase 07) |
| `config/` | 타입 지정 런타임 설정 |
| `data/fixtures/` | 큐레이션한 버전 관리 데모 fixture |
| `data/raw/`, `data/processed/` | 로컬 입력 / 산출물 (git 무시) |
| `docs/` | PRD, 아키텍처, contract, 평가, 상태 |
| `tests/` | `unit/`, `integration/`, `e2e/` |

## 예측 결과 및 해석 (Phase 06)

실데이터(Citi Bike JC, 2026년 6월)로 돌린 결과입니다. 목표는 `departures`(H3 Zone x 로컬 시간,
1시간 앞 forecast). 평가는 rolling-origin — 최근 72시간을 손대지 않은 out-of-sample test로 빼고,
그 앞 구간을 expanding-window 3-fold로 CV했습니다. 랜덤 분할은 쓰지 않았고 seed는 42입니다.
usable row 30,947개 / 139개 Zone, dev 26,918 · test 4,029, B1 feature 32개.

전 수치는 실제 실행에서 나온 값이며, 재현은 `make evaluate`로 가능합니다. 원본은
`reports/phase06_results.json`, 상세 해석은 [docs/EVALUATION_PROTOCOL.md](docs/EVALUATION_PROTOCOL.md).

### 지표를 왜 이렇게 골랐나

이 데이터의 성질에서 지표가 정해졌습니다. `departures`는 **평균 2.7 / 중앙값 2 / 최대 87**의
간헐적 카운트 수요로, **0인 시간이 20.2%**, 2 이하가 64%이고, Zone별 평균 규모가 0~12로 극단적으로
다릅니다.

- **percentage 계열(MAPE·sMAPE)은 탈락** — 0으로 나눠 폭발합니다.
- **WAPE**(Σ\|y−ŷ\|/Σ\|y\|) — 합산 정규화라 0에 강하고, 수요 큰 Zone·시간대의 오차를 자동 가중.
- **MASE**(seasonal naive 대비) — Zone 규모가 제각각이라 **scale-free** 지표가 필수. <1이면 naive보다 나음.
- **MAE** — "평균 몇 대 틀리나"의 직관적 보조 지표.
- **peak direction accuracy** — 재배치는 크기보다 **오르내림 방향**이 중요.
- **bias**(평균 오차) — 체계적 과소예측 = 품절 위험을 감지.
- **OCS(Operational Cost Score)** — 아래의 **데이터/도메인 맞춤 지표**.

### 알고리즘 leaderboard (GridSearch, CV WAPE 기준 정렬)

OCS는 아래 "맞춤 지표" 절 참고(shortage 2.0 / overflow 1.0). bias = 평균(ŷ − y), 음수면 과소예측.

| 알고리즘 | CV WAPE | test WAPE | test MASE | test OCS | bias | peak-dir |
|---|---|---|---|---|---|---|
| _B0 seasonal naive_ | - | 0.6584 | 1.0125 | 1.1473 | −0.867 | 0.559 |
| **knn** ⭐(CV 선택) | 0.5438 | 0.5161 | 0.7936 | 0.8571 | −0.451 | 0.632 |
| extra_trees | 0.5507 | 0.4922 | 0.7569 | **0.7809** | −0.231 | 0.640 |
| hist_gradient_boosting | 0.5522 | 0.4974 | 0.7649 | 0.7897 | −0.237 | 0.646 |
| random_forest | 0.5533 | 0.5047 | 0.7761 | 0.8015 | −0.241 | 0.642 |
| gradient_boosting | 0.5556 | 0.4972 | 0.7646 | 0.7905 | −0.243 | 0.636 |
| ridge | 0.5853 | 0.5268 | 0.8101 | 0.8559 | −0.357 | 0.626 |

![알고리즘 비교](docs/img/phase06_algorithm_comparison.png)

### OCS — 데이터/도메인 맞춤 지표

수요 예측 오차는 **방향이 비대칭**입니다. **과소예측**(ŷ<y)은 자전거 부족 → 품절(rider가 자전거를
못 찾음), **과대예측**(ŷ>y)은 dock 초과·헛된 재배치. 보통 부족이 더 아픕니다. 그래서:

$$\text{OCS} = \frac{c_{short}\sum\max(y-\hat y,0) + c_{over}\sum\max(\hat y-y,0)}{\sum y}$$

기본 $c_{short}=2,\ c_{over}=1$ ([config/forecasting.py](config/forecasting.py), §11.5·§14의 비용
가중치). 합산 정규화라 **0에 강하고 scale-free**이며, **두 비용이 같으면 정확히 WAPE로 환원**됩니다 —
WAPE를 재배치 목적함수 쪽으로 굽힌 원리적 일반화이고, Phase 08 비용 모델과 직접 이어집니다.

**핵심 발견 — 맞춤 지표가 순위를 바꿉니다.** WAPE로 뽑은 knn은 OCS에서는 학습 모델 중 **가장 나쁩니다**
(0.857). knn이 더 심하게 과소예측(bias −0.451, 부족 3,730대)하는 반면, tree 계열은 덜 과소예측
(extra_trees bias −0.231, 부족 3,157대 → OCS 0.781로 최고)하기 때문입니다. **모든 모델이 과소예측
(음의 bias)** 이라 품절 위험이 구조적으로 존재하고, B0는 특히 심합니다(bias −0.867, OCS 1.147).
즉 정확도(WAPE)만 보면 knn이지만, **품절 비용까지 보면 extra_trees가 운영상 더 낫다** — 이것이 이
데이터에 맞춘 지표를 따로 둔 이유입니다. (선택 자체는 프로토콜대로 CV WAPE로 하되, 운영 관점의
재순위를 함께 보고합니다.)

### 모델 해석

**best 모델은 CV WAPE 기준으로 knn**(`n_neighbors=30`, `weights=distance`)이 뽑혔습니다. test에서
WAPE 0.5161, MASE 0.7936 — MASE가 1보다 작으니 주간 seasonal naive를 이깁니다(B0 대비 test WAPE
약 21.6% 개선). 다만 정직하게 덧붙이면, 손대지 않은 test 창에서는 extra_trees(0.4922)와 boosting
계열(약 0.497)이 knn을 근소하게 앞섭니다. 선택은 프로토콜대로 **test가 아닌 CV로** 했기 때문에
knn을 대표 모델로 보고합니다. tree/knn 계열은 test WAPE 0.49~0.53 구간에 촘촘히 모여 있어, 이
데이터에서는 알고리즘 종류보다 feature가 성능을 좌우한다는 뜻입니다.

### best hyperparameter 해석

| 파라미터 | 값 | 의미 |
|---|---|---|
| `n_neighbors` | 30 | 예측에 평균 내는 이웃 수. 30개로 크게 잡아 노이즈에 강하고 매끄러운 예측. |
| `weights` | distance | 가까운 이웃일수록 큰 가중치 → 지역 demand 수준을 더 정확히 반영. |

이웃을 5·15가 아니라 30으로 크게, 그리고 거리 가중을 준 조합이 CV에서 가장 안정적이었습니다. 개별
시점의 튐(noise)에 휘둘리지 않고 최근·유사 패턴을 넓게 평균하는 쪽이 이 수요 데이터에 맞았다는 신호입니다.

### feature 해석 (permutation importance, test holdout 기준)

feature를 하나씩 섞었을 때 WAPE가 얼마나 나빠지는지로 측정했습니다(값이 클수록 의존도 큼).

| 순위 | feature | 중요도 | 의미 |
|---|---|---|---|
| 1 | `dep_lag_1` | 0.0202 | 직전 시간 departures — 단기 지속성 |
| 2 | `dep_lag_168` | 0.0156 | 1주일 전 같은 시각 — 주간 seasonality |
| 3 | `arr_lag_1` | 0.0146 | 직전 시간 arrivals |
| 4 | `dep_lag_24` | 0.0144 | 하루 전 같은 시각 |
| 5 | `cal_hour_cos` | 0.0130 | 시각(hour-of-day) 순환 인코딩 |
| 6 | `arr_roll_mean_3` | 0.0121 | 최근 3시간 arrivals 평균 |
| 7 | `cal_is_evening_rush` | 0.0120 | 저녁 러시(16-18시) |
| 8 | `dep_expanding_mean` | 0.0117 | 해당 Zone의 누적 평균 demand(규모) |

해석하면, **단기 지속성(직전 시간)이 가장 강하고**, 그다음이 주간(168h)·일간(24h) seasonality,
그리고 시각·저녁 러시 같은 calendar 신호와 Zone별 demand 규모입니다. EDA에서 확인한 "평일/주말
차이는 총량보다 타이밍(저녁 러시)에서 온다"는 결론과 일치합니다.

![feature importance](docs/img/phase06_feature_importance.png)

**feature selection**: 상위 12개만 남겨 다시 학습하면 test WAPE 0.512로, 32개 전체(0.5161)와
동등하거나 오히려 근소하게 낫습니다. 예측력의 대부분이 소수의 history feature에 몰려 있다는 뜻입니다.

### ablation B0–B4 (정직한 보고)

| 단계 | feature | WAPE | MAE | MASE |
|---|---|---|---|---|
| B0 (seasonal naive) | - | 0.6584 | 1.787 | 1.0125 |
| B1 (demand history + calendar) | 32 | 0.5161 | 1.401 | 0.7936 |
| B2 (+ article counts) | 34 | 0.5161 | 1.401 | 0.7936 |
| B3 (+ LLM event features) | 37 | 0.5161 | 1.401 | 0.7936 |
| B4 (+ graph-propagated features) | 40 | 0.5161 | 1.401 | 0.7936 |

**정직한 읽기**: 이 6월 평가 창에서 유일한 curated 이벤트는 데이터보다 뒤인 2026-07-12라, 가용성
규칙(§5.2)에 따라 모든 event/graph feature가 0이 됩니다. runner가 창의 마지막 cutoff
(2026-06-30 23:00)에서 `build_graph_features`를 호출해 snapshot 0개임을 실제로 확인했고, 그래서
B2–B4는 B1과 완전히 같고 B4−B1 forecast delta도 0입니다. 즉 **이벤트 효과는 이 창에서는 입증
불가**이며, 입증하려면 curated 이벤트와 겹치는 평가 구간이 필요합니다(가짜 뉴스 생성은 §22로 금지).
event-aware 로직 자체는 as-of 누수 테스트(`tests/unit/test_graph_features.py`, 14:01→14:00
회귀 포함)로 별도 검증됩니다. 한계는 [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) 참고.

## 재배치 & 양자 리서치 모드 (Phase 08)

예측을 실제 운영 조치로 잇는 **Act** 단계입니다(§13, §14). 각 station은 현재 재고·용량·목표(target)
재고를 갖고, 목표를 맞추도록 이동 예산(`vehicle_capacity`) 안에서 자전거를 정수 단위로 옮깁니다.

- **목적함수(비대칭, §14.1)** — `shortage_cost·부족 + overflow_cost·과잉 + distance_cost·이동거리`.
  부족(품절 → trip 손실)을 과잉보다 무겁게(기본 3:1) 둡니다. Phase 06의 OCS 지표와 같은 비대칭 철학.
- **solver 사다리** — ① Greedy(항상 feasible, do-nothing보다 나쁘지 않음) → ② MILP(`scipy.optimize.milp`,
  정확 최적) → ③ enumeration oracle(작은 instance 완전 탐색). 테스트에서 **MILP 비용 == enumeration
  비용**(최적)이고 greedy 이하임을 검증합니다.
- **feasibility 명시(§14.1)** — 출발지 재고 초과, 도착지 용량 초과, 음수/비정수 이동, 차량 용량 초과를
  명시적으로 거부하고 사람이 읽는 사유를 반환합니다. 계획은 이 검사를 통과해야만 화면에 노출됩니다.
- **이벤트 연동** — 이벤트가 노출된 zone은 as-of `demo-heuristic-v1` forecast delta만큼 target이
  올라가 부족이 생기고, solver가 조용한 zone(Grove St, Exchange Place)에서 자전거를 옮겨옵니다.
  이벤트 전에는 target=base라 계획이 비어 있습니다. (측정된 Phase 06 모델이 아니라 라벨된 데모 heuristic)
- **양자 리서치 모드(§14.2, 리서치 전용)** — 작은 instance를 QUBO로 매핑하고, **QUBO 최적 == 완전
  탐색 최적**임을 검증합니다(모든 비트 벡터에서 에너지 일치, crafted instance에서는 MILP 계획과 일치).
  QAOA는 선택(`qiskit` 없으면 "unavailable" 경로 + 사유 명시 skip). 시뮬레이터이며 하드웨어가 아니고,
  **양자 우위 주장은 하지 않습니다.**

자세한 매핑과 검증은 [docs/OPTIMIZATION.md](docs/OPTIMIZATION.md)에, 90초 골든패스는
[docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)에 있습니다. 한계는
[docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) 참고.

## V1 (모델·추천·실험·이상탐지·라이브)

v0 위에 backward-compatible 증분으로 V1을 구현했습니다 — 측정된 모델 스토리(B0–B4),
어텐션 듀얼인코더 추천 + reranker + 정책, 동적 인센티브·정책 시뮬레이션, 클러스터드 스위치백 실험,
이상 탐지, 라이브 섀도(pending label), **FAISS 뉴스 벡터 스토어**(누적 수집·의미 검색·같은 사건 클러스터).
웹 콘솔은 8개 화면. 모든 값은 measured / pending / simulated / blocked 중 하나로 정직하게 표기합니다.

```bash
make v1-collect-news-live     # (opt-in) 실제 GDELT 뉴스 수집 → FAISS 스토어에 누적
make v1-build-event-features  # 증분 그래프 피처 == 전체 재빌드 검증
make v1-evaluate-anomalies    # 4개 이상 탐지기 (합성 결함 시나리오)
make v1-experiment-dry-run    # A/A + 정책 스위치백 (simulated)
make v1-live-fixture          # 라이브 섀도 마이크로배치 (pending label)
make v1-news-vectorstore      # FAISS 의미 검색 + 같은 사건 클러스터
```

전체 계획·실행 로그·감사는 [docs/V1_PORTFOLIO_SUMMARY.md](docs/V1_PORTFOLIO_SUMMARY.md),
[docs/V1_DEMO_SCRIPT.md](docs/V1_DEMO_SCRIPT.md),
[docs/V1_EXECUTION_LOG.md](docs/V1_EXECUTION_LOG.md), `reports/v1/V1_FINAL_AUDIT.md` 참고.

## V2 사용성 업데이트 (UI·검색·운영 통계)

V1 위에 backward-compatible 증분으로 사용성에 초점을 맞춘 업데이트를 더했습니다. 새 모델·가격·실험
주장은 없으며, 모든 값은 오프라인에서 계산되고 수요 변화(Δ)는 라벨이 붙은 데모
heuristic(`demo-heuristic-v1`)입니다.

- **라이더 홈 리디자인** — 공유자전거 앱 스타일의 검색바 + 필터 칩 + 대여소 리스트 + 상세 시트.
- **대여소 검색** — `GET /v2/rider/stations/search?q=…` (한글/영문/별칭/오타 허용 부분일치;
  재고는 항상 운영 fixture에서 hydrate, 검색어에서 추론하지 않음). 빈 검색어는 전체를 가용성순 정렬.
- **운영 통계** — `GET /v2/operator/statistics` (시스템 가동률, 가용성 분포, 부족 부하, 이벤트 구성,
  수요 Δ 분포, 지역별 상세)를 새 `/statistics` 화면에서 시각화.
- **이벤트 윈도우 타임라인** — `GET /v2/operator/timeline` (재생 윈도우 12–18시를 매 시각 as-of로
  재계산한 부족·Δ·이벤트 시계열)을 인라인 SVG 차트로 시각화. 이벤트 공개 이전 flat 구간이 leakage
  경계를 그대로 보여줍니다.
- **추가 자전거 최적 분배** — `POST /v2/operator/rebalancing/allocate` (운영자가 추가 자전거 **m**대를
  입력하면, 부족한 대여소에 어떻게 나눠야 이익이 최대일지 계산). 비대칭 목적(부족 3 : 과잉 1)이 분리·볼록
  이라 greedy 한계이익 배분이 전역 최적이며 완전탐색과 일치 검증. 목표 충족 뒤 남는 자전거는 창고 보유로
  정직 보고. `/rebalancing` 화면 상단의 "추가 자전거 최적 분배" 카드에서 m을 입력합니다.

```bash
make api    # v1 + v2 엔드포인트 (오프라인, :8000)
curl "127.0.0.1:8000/v2/rider/stations/search?q=시청"
curl "127.0.0.1:8000/v2/operator/statistics"
curl "127.0.0.1:8000/v2/operator/timeline"
make web    # /  (라이더 홈)  및  /statistics  (운영 통계)
```

**휴대폰에서 보기 (같은 Wi-Fi):** 라이더 UI는 모바일 반응형입니다. 두 개의 터미널에서 아래를 실행한 뒤,
폰 브라우저에서 `http://<PC IP>:3000` 으로 접속하세요. 여전히 완전 오프라인(키 불필요)이며 로컬 네트워크만
접근할 수 있습니다.

```bash
make api-lan                      # API를 0.0.0.0:8000 으로 (LAN 노출)
make web-lan LAN_IP=192.168.0.10  # PC의 실제 IP로 교체 (macOS: ipconfig getifaddr en0, Linux: hostname -I)
```

자세한 스펙과 재현 방법은 [docs/V2_UX_UPDATE.md](docs/V2_UX_UPDATE.md), 실제 배포(라이브 뉴스 동기화·
Elasticsearch·LAN 등)는 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) 참고.

## 상태

현재 진행 중인 단계와 검증된 명령, 남은 걸림돌은 [docs/STATUS.md](docs/STATUS.md)에서 확인하세요.

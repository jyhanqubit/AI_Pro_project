# Agent experiments — 실측 보고서

모든 숫자는 아래 명령을 실제로 실행해 나온 값이며, 각 결과 JSON 에 커밋 해시와 명령이 적혀 있습니다.
실행하지 못한 항목은 **미실행** 으로 표시합니다.

## 작업 1. MCP 토큰 측정과 결과 요약 비교

- 산출 스크립트: `python -m experiments.mcp_tokens` → `reports/agent_experiments/mcp_tokens.json`
- 조건: 커밋 `fb5d943` 기준 작업 트리(결과 JSON 의 `git_commit` 참고), 전송 `mcp_stdio`(실제
  `services.mcp.server` 를 stdio 로 띄워 호출), cutoff `2026-07-12T18:00:00-04:00`(데모 창 끝),
  mode `historical_replay`, seed 42(난수 사용 없음), 토크나이저 `tiktoken cl100k_base`(근사, 제공사 토크나이저와
  다를 수 있음), 직렬화 compact UTF-8 JSON, `freshness` 상수 치환.

### 1-1. 도구 정의 토큰 (5개 도구, `services/mcp/server.py`)

| 도구 | name+description+input_schema | +output_schema 포함 |
|---|---:|---:|
| get_graph_context | 102 | 806 |
| get_operator_statistics | 80 | 588 |
| get_metric | 128 | 663 |
| get_model_forecast | 76 | 587 |
| get_pricing_quotes | 477 | 1,342 |
| **합계** | **865** | **3,988** |

output_schema 를 함께 보내는 클라이언트라면 정의 토큰이 4.6배가 됩니다. `get_pricing_quotes` 는 `PricingRules`
중첩 스키마 때문에 입력 스키마만으로도 전체의 55% 를 차지합니다.

### 1-2. 시나리오별 원본 vs 요약 응답

| 시나리오 | 도구 (정의 토큰) | 원본 응답 | 요약 응답 | 감소율 | 답 보존 확인 |
|---|---|---:|---:|---:|---|
| A. 특정 zone 다음 1시간 예측 조회 | get_model_forecast (76) | 1,067 | 263 | 75.4% | zone 892a107216bffff 예측 8.3 양쪽 동일, serving_hour·algorithm·run_id·claim_status 보존 |
| B. 이벤트 근거 조회 (cutoff 기준) | get_graph_context (102) | 328 | 324 | 1.2% | 이벤트 2건의 id·type·근거 문장·최대 delta zone 동일, cutoff 보존 |
| C. 운영 상태(부족/급등, 재배치 입력) 조회 | get_operator_statistics (80) | 5,265 | 664 | 87.4% | 부족 정류장 17, 부족 147대, 이용률 0.48, 최대 급등 zone 892a10723b7ffff(delta 4.5) 동일 |
| D. (보조) 최적 재배치 정책 지표 | get_metric (128) | 74 | 74 | 0.0% | 이미 enveloped 숫자 하나라 요약 변형 없음 |

요약 방식(`experiments/mcp_summary.py`): provenance 블록 유지, 집계값 유지, 질문에 필요한 행만(A: 요청 zone,
B: 이벤트당 최대 delta zone 1개 + zone 수, C: 급등·부족 상위 3개 zone, 6개 필드), 원본은 `full_result_ref`
(tool, args, run_id, artifact_id) 로 참조. 요약 도구는 별도 서버 `experiments/mcp_summary_server.py`
(3개 도구, 정의 358 토큰)에 두었고 기존 5개 도구는 그대로입니다.

### 1-3. 도구를 단계별로만 노출했을 때 (정의 토큰)

| 시나리오 | 5개 전부 | 필요한 도구만 | 감소율 | 카탈로그(이름+첫 문장, 210) + 선택 도구 | 감소율 |
|---|---:|---:|---:|---:|---:|
| A | 865 | 78 | 91.0% | 288 | 66.7% |
| B | 865 | 104 | 88.0% | 314 | 63.7% |
| C | 865 | 82 | 90.5% | 292 | 66.2% |
| D | 865 | 130 | 85.0% | 340 | 60.7% |

(필요한 도구만 노출한 값이 1-1 의 개별 값보다 2 토큰 큰 것은 리스트 괄호 때문입니다.)

### 결론 (3줄)

1. 토큰은 도구 정의가 아니라 **응답** 에서 나간다. 큰 응답(운영 상태 5,265)은 집계 + 상위 N 행 + 참조로 87% 를
   줄이면서 질문의 답(부족 수, 이용률, 최대 급등 zone)을 그대로 보존했다.
2. 응답이 이미 작으면(이벤트 2건 328, 지표 74) 요약 블록의 고정 비용 때문에 이득이 없다(1.2%, 0%). 요약은
   행 수가 많은 도구에만 붙이는 것이 맞다.
3. 도구 정의는 필요한 도구만 노출하면 85~91%, 카탈로그 뒤 선택 방식이면 61~67% 줄고, output_schema 를
   함께 보내는 클라이언트에서는 절대량이 4.6배라 단계별 노출의 효과가 더 커진다.

## 작업 2. SHAP 설명 모듈

- 산출 스크립트: `python -m experiments.shap_explain --months 2026-08 2026-09 --n 3000 --seed 42`
  → `reports/agent_experiments/shap_explain.json`
- 모델: 커밋된 승격 모델 `reports/v2/holdout/promoted_model.joblib` (run `run_v2-01_20260816T061758Z_827818f6`,
  HistGradientBoostingRegressor lr 0.1 / depth 8 / max_iter 300, 조기 종료로 154개 트리, 학습 범위 2026-07-31 23:00 까지,
  피처 32개 dfv1). API 가 쓰는 버전 검사 로더로 로드.
- 데이터: 저지시티 트립 `JC-202601 … JC-202609` 를 `make download-citibike JC=1` 로 받아 저장소 파이프라인으로 만든
  패널(7월까지 226,955행 / 219 zone; 승격 아티팩트의 226,953 / 219 와 2행 차이, 월 경계 dense index 차이로 추정).
  설명 대상은 **학습 범위 밖인 2026-08, 09 의 81,100행에서 seed 42 로 뽑은 3,000행**(105 zone). 샘플 WAPE 0.4925.
- Explainer: `shap.TreeExplainer` 가 sklearn HGB 를 지원해 그대로 사용(shap 0.51.0). 대체 경로 불필요.
  입력은 파이프라인의 median imputer 를 거친 행렬(모델이 실제로 보는 값). SHAP 합 + base 가 예측과 일치함을 테스트로 확인.

### 2-1. 글로벌: 평균 |SHAP| 상위 10 (3,000행)

| 순위 | 피처 | 평균 \|SHAP\| | 누수 판정 (`pipelines/features/lags.py`, `calendar.py` 대조) |
|---:|---|---:|---|
| 1 | dep_lag_1 | 0.410 | series[t-1] (l.28-30): t 이전 값만, 안전 |
| 2 | dep_lag_168 | 0.372 | series[t-168]: 안전 |
| 3 | dep_lag_24 | 0.298 | series[t-24]: 안전 |
| 4 | cal_hour_cos | 0.265 | 예측 시각 t 의 달력값, 사전에 알려짐, 수요 정보 아님: 안전 |
| 5 | arr_roll_mean_24 | 0.241 | mean(series[t-24:t]) (l.34), 창이 t-1 에서 끝남: 안전 |
| 6 | dep_roll_mean_3 | 0.230 | mean(series[t-3:t]): 안전 |
| 7 | arr_lag_1 | 0.165 | series[t-1]: 안전 |
| 8 | cal_hour_sin | 0.146 | 달력값: 안전 |
| 9 | arr_roll_mean_3 | 0.144 | mean(series[t-3:t]): 안전 |
| 10 | net_cumsum_day | 0.141 | 같은 날 index < t 인 net_flow 합 (l.56-57): 안전 |

상위 10개 중 예측 시점 t 이후 정보를 쓰는 피처는 없습니다. 모든 지연/롤링 피처는 `j = i - k`, `s[i-w:i]` 처럼 t 를
제외하고 계산되고, 달력 피처는 t 의 시각 자체입니다.

### 2-2. 로컬: 대표 예측 3건의 상위 5 기여

| 대표 행 | zone / 시각 | 실제 | 예측 | 상위 5 기여 (값 → SHAP) |
|---|---|---:|---:|---|
| 최고 예측 | 892a1072e7bffff, 08-19 17:00 | 40 | 50.14 | dep_lag_168 51 → +12.72, dep_lag_1 17 → +8.26, dep_lag_24 37 → +7.20, net_cumsum_day 100 → +6.26, cal_is_evening_rush 1 → +1.99 |
| 중앙 예측 | 892a107233bffff, 08-29 06:00 | 2 | 1.87 | dep_lag_24 6 → +0.67, dep_lag_1 0 → −0.41, dep_lag_168 0 → −0.39, arr_roll_mean_24 3.25 → +0.23, dep_roll_mean_3 0 → −0.21 |
| 최저 예측 | 892a107253bffff, 09-30 09:00 | 0 | −0.05 | dep_expanding_mean 0 → −0.52, arr_roll_mean_24 0.04 → −0.31, dep_lag_1 0 → −0.29, dep_lag_168 0 → −0.27, dep_lag_24 0 → −0.27 |

최고 예측 행은 지난주 같은 시각 51대, 어제 37대의 피크가 올해 17시 퇴근 러시를 50 대로 밀어올린 경우이고, 실제는 40 이었습니다.
최저 행은 예측이 음수(−0.05)로 나와 서빙 단계의 0 클리핑이 필요함을 보여 줍니다.

### 2-3. 기본 importance 와 SHAP 순위 비교

기본 importance 두 가지: (1) 트리 내부 총 split gain(`_predictors` 노드의 gain 합, 모델 자체 구조),
(2) permutation importance(MAE, 5회 반복, seed 42, 같은 3,000행). SHAP 상위 12 기준:

| 피처 | SHAP 순위 | gain 순위 | permutation 순위 | 비고 |
|---|---:|---:|---:|---|
| dep_lag_1 | 1 | 2 | 3 | |
| dep_lag_168 | 2 | 1 | 2 | |
| dep_lag_24 | 3 | 3 | 4 | |
| cal_hour_cos | 4 | 9 | 1 | **차이 큼** (gain 는 낮게, permutation 은 1위) |
| arr_roll_mean_24 | 5 | 5 | 5 | |
| dep_roll_mean_3 | 6 | 6 | 7 | |
| arr_lag_1 | 7 | 8 | 12 | |
| cal_hour_sin | 8 | 11 | 6 | |
| arr_roll_mean_3 | 9 | 7 | 10 | |
| net_cumsum_day | 10 | 4 | 8 | **차이 큼** (gain 는 4위, SHAP 는 10위) |
| net_roll_mean_24 | 11 | 13 | 11 | |
| cal_is_evening_rush | 12 | 10 | 14 | |

차이가 큰 피처(SHAP 와 gain 순위 차 5 이상, 둘 중 하나가 10위 안): `cal_hour_cos`, `net_cumsum_day`. gain 은 학습 시
분할 이득의 합이라 값 범위가 넓고 자주 분할되는 누적 피처(net_cumsum_day, 분할 327회)를 높게 보고, SHAP 와 permutation
은 실제 예측 변화 기준이라 시각(cal_hour_cos)을 높게 봅니다.

### 결론 (3줄)

1. 승격 모델의 예측은 1시간 전, 1주 전, 1일 전 출발 수 세 개가 지배하고(평균 |SHAP| 0.41/0.37/0.30), 그 다음이 시각 달력과
   24시간 도착 평균입니다. 뉴스/이벤트 피처는 승격 모델 입력(32개 B1)에 없습니다.
2. 상위 10 피처 모두 `lags.py` 의 인덱스 규칙(t 제외)과 대조해 누수 아님을 확인했습니다.
3. gain 기준 importance 는 SHAP 와 두 피처에서 크게 어긋나므로(cal_hour_cos, net_cumsum_day), 설명에는 gain 이 아니라
   SHAP 또는 permutation 을 써야 합니다.

## 작업 3. 재학습 판단 (PSI + 성능)

- 산출 스크립트: `python -m experiments.retrain_gate --baseline-months 2026-01 2026-02 2026-03 2026-04 2026-05 --drop-pct 5.0 --seed 42`
  → `reports/agent_experiments/retrain_gate.json`
- 데이터: 작업 2 와 같은 저지시티 패널 2026-01~09 (usable 308,055행, 246 zone). 기준 분포 = 1~5월 145,354행.
  비교 구간 = 6, 7, 8, 9월. 챔피언 = 커밋된 승격 모델(최종 학습 범위 7월 말까지라 6, 7월은 챔피언에게 in-sample,
  8, 9월은 out-of-sample).
- PSI: 연속형은 기준 분포의 10분위 경계(중복 제거), 고유값 10개 이하는 값 구간, NaN 은 별도 구간, eps 1e-4.
  주요 피처 = 챔피언 트리의 총 gain 상위 12개.
- 성능 기준: 커밋된 multi-holdout 평균 WAPE 0.4974(5~7월 out-of-sample). 월 WAPE 가 이보다 **5% 넘게** 나쁘면 하락.
- 규칙: 주요 피처 max PSI < 0.10 이고 하락 없음 → 그대로 사용, 0.10~0.25 또는 하락 → 재학습, ≥ 0.25 → 신규 검토.

### 3-1. 월별 PSI 와 챔피언 성능

| 월 | 행 | max PSI (피처) | PSI ≥ 0.1 인 피처 (32개 중) | 챔피언 WAPE | 기준 대비 | in-sample | 판정 |
|---|---:|---|---|---:|---:|---|---|
| 2026-06 | 40,442 | 0.230 (arr_roll_mean_24) | arr_expanding_mean, arr_roll_mean_24, dep_expanding_mean, dep_roll_mean_24, member_share_lag_168 | 0.4644 | −6.64% | 예 | 재학습 |
| 2026-07 | 41,159 | 0.185 (arr_roll_mean_24) | 같은 5개 | 0.4811 | −3.27% | 예 | 재학습 |
| 2026-08 | 41,823 | 0.201 (arr_roll_mean_24) | 같은 5개 | 0.4944 | −0.59% | 아니오 | 재학습 |
| 2026-09 | 39,277 | 0.177 (arr_roll_mean_24) | 위 5개 + arr_lag_168, dep_lag_168 | 0.4825 | −2.99% | 아니오 | 재학습 |

주요 12개 피처 중 PSI 가 0.1 을 넘는 것은 매달 `arr_roll_mean_24` 하나(9월은 `dep_lag_168` 0.117 추가)이고, 나머지는
0.01~0.10 입니다. 이동 평균과 누적 평균이 흔들리는 것은 여름 수요 수준이 1~5월 기준보다 높아진 **계절 수준 이동**이며,
달력 피처 PSI 는 0.002~0.026 으로 구성 변화가 없습니다. 성능은 네 달 모두 기준보다 좋아 하락은 없습니다.

### 3-2. 챌린저 vs 챔피언 (같은 평가 월, 같은 알고리즘과 하이퍼파라미터, seed 42)

| 평가 월 | 챌린저 학습 구간 | 학습 행 | 챔피언 WAPE | 챌린저 WAPE | 상대 | 챌린저 우세 |
|---|---|---:|---:|---:|---:|---|
| 2026-08 | 2026-01..07 (챔피언과 같은 범위, 재적합 일관성 확인) | 226,955 | 0.4944 | 0.4953 | +0.19% | 아니오 |
| 2026-09 | 2026-01..08 (최근 8월 포함) | 268,778 | 0.4825 | 0.4799 | −0.55% | 예 |

### 결론 (3줄)

1. 규칙대로면 6~9월 모두 "재학습" 구간이지만, 그 근거는 성능 하락이 아니라 24시간 이동 평균의 PSI 0.18~0.23 뿐이고
   챔피언 WAPE 는 네 달 모두 기준(0.4974)보다 낮습니다.
2. 최근 월(8월)을 넣어 재학습한 챌린저는 9월에서 WAPE 0.4825 → 0.4799 로 0.55% 좋아졌고, 같은 범위를 재적합한 챌린저는
   8월에서 0.19% 나빠져 재적합 잡음 수준입니다. 즉 재학습 이득은 있으나 작습니다.
3. 운영 판단: 월 단위 재학습을 자동화하되 승격은 "챌린저가 같은 평가 월에서 더 좋을 때"로 묶어야 하고, PSI 단독
   경보는 계절 이동을 재학습 신호로 오인하므로 성능 조건과 반드시 함께 봐야 합니다.

## 공통 조건

- 커밋: 각 JSON 의 `git_commit` (실험 1 `fb5d943+dirty`, 실험 2·3 `6457278+dirty`; dirty 는 당시 작업 트리에 해당 실험
  코드가 아직 커밋되지 않았다는 뜻). 재현은 이 보고서가 들어간 커밋에서 `make exp-mcp-tokens`, `make exp-shap`,
  `make exp-retrain-gate`.
- 시드 42. 토크나이저 tiktoken cl100k_base(근사). 실험 2·3 데이터 구간은 위 표 참고. 기존 모델, 지표, 엔드포인트, 테스트는
  변경하지 않았습니다.

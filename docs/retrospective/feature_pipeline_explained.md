# ShockFlow AI 피처 설명서: 수요 이력, 기상, 뉴스 이벤트가 모델 입력이 되기까지

이 문서는 저장소 코드 기준으로 세 가지를 설명한다. 기존 수요예측 피처와 결과값을 만드는 방법, NOAA 기상을 피처로 붙이는 방법, 뉴스를 LLM 으로 구조화해 숫자 피처로 바꾸는 방법이다. 숫자는 전부 저장소의 결과 파일에서 가져왔다.

## 1. 전체 흐름

```text
Citi Bike 트립 CSV
  → 수집기 검증 (pipelines/collectors/citibike.py)
  → H3 zone × 현지 1시간 집계 (pipelines/features/aggregate.py)        ← 타깃 3개
  → 지연·롤링·달력 피처 (pipelines/features/lags.py, calendar.py)       ← 기본 피처 32개
  → [선택] 기상 전날 값 결합 (ml/forecasting/weather_lift.py)            ← 8개
  → [선택] 뉴스 → LLM 이벤트 → as-of 조인 (pipelines/events, dataset.py) ← 2 + 3 + 3개
  → HistGradientBoosting 학습, rolling-origin 평가 (ml/forecasting/h3_multiholdout.py)
  → 승격 모델 + 서빙 스냅숏 → GET /v2/model/forecast
```

한 행은 "zone 하나의 한 시간" 이다. 행의 타깃은 그 시간의 출발 수이고, 피처는 그 시간이 시작되기 전까지 알 수 있는 값만 쓴다. 이 원칙 하나가 아래 모든 변환의 기준이다.

## 2. 기존 수요예측 피처

### 2-1. 타깃: 트립을 zone × 시간으로 집계

`aggregate_demand` 는 트립마다 출발 좌표를 H3 해상도 9(평균 변 길이 약 174 m) 셀로 바꾸고, 출발 시각을 America/New_York 현지 시간으로 바꿔 한 시간 단위로 내린다. 도착도 같은 방식으로 센다. 그래서 셀 하나에 세 숫자가 생긴다.

```text
departures = 그 zone 에서 그 시간에 출발한 트립 수
arrivals   = 그 zone 에 그 시간에 도착한 트립 수
net_flow   = arrivals - departures
```

주 타깃은 departures 다. 회원 여부가 있으면 departures_member, departures_casual 도 같이 센다. 수집기는 좌표 결측, 위도 범위 초과, 종료 시각이 시작보다 앞선 행을 버리되 사유별로 세어 메타데이터에 남긴다.

### 2-2. 기본 피처 32개 (B1)

`build_demand_features` 는 zone 마다 빈 시간이 없는 시간 격자를 만들고(없는 시간은 수요 0), 시각 t 의 행에 t 이전 값만으로 피처를 채운다. 설정은 `config/features.py` 에 있다.

| 묶음 | 컬럼 | 만드는 법 |
|---|---|---|
| 지연 (9개) | dep/arr/net_lag_1, _24, _168 | series[t−k]. 1시간 전, 어제 같은 시각, 지난주 같은 시각 |
| 이동 평균 (6개) | dep/arr/net_roll_mean_3, _24 | mean(series[t−w : t]). 창이 t−1 에서 끝나도록 한 칸 민 값 |
| 모멘텀 (2개) | dep/arr_momentum | 직전 3시간 평균 ÷ 직전 24시간 평균 |
| 누적 평균 (2개) | dep/arr_expanding_mean | t 이전 모든 시간의 평균 (zone 의 수요 규모) |
| 당일 누적 (1개) | net_cumsum_day | 같은 현지 날짜에서 t 이전 시간의 net_flow 합 (재배치 압력) |
| 회원 비율 (2개) | member_share_lag_24, _168 | 어제·지난주 같은 시각의 회원 출발 비율 |
| 달력 (10개) | cal_hour_of_day, cal_day_of_week, cal_is_weekend, cal_is_morning_rush(7~9시), cal_is_evening_rush(16~18시), cal_is_holiday, cal_hour_sin/cos, cal_dow_sin/cos | 예측 대상 시각 t 자체의 달력값. 미래 정보가 아니다 |

처음 한 주는 lag_168 이 없어서 학습 행렬에서 뺀다(`usable_frame`, 필수 컬럼 dep_lag_1, dep_lag_24, dep_lag_168, dep_roll_mean_24). 저지시티 2026-01~07 패널은 이 단계에서 226,953행, 219개 zone 이 된다.

### 2-3. 결과값을 만드는 방법

**학습과 평가.** 랜덤 분할은 쓰지 않는다. 학습 구간을 시간 순으로 늘리며 다음 달을 예측하는 rolling-origin 으로 5월, 6월, 7월 세 창을 돌린다. 후보는 ridge 와 HistGradientBoosting 이고, 4월까지의 개발 구간에서 GridSearch 로 고른 결과 HGB(learning_rate 0.1, max_depth 8, max_iter 300)가 CV WAPE 0.5557 로 승격됐다. 세 창 평균 WAPE 0.4974 ± 0.0074, MASE 0.871. 같은 5월 창에서 seasonal naive 는 WAPE 0.688 이다. 승격 모델은 7월 말까지 전체 행으로 다시 적합해 `promoted_model.joblib` 로 저장하고, 함께 저장한 scikit-learn 버전이 다르면 로더가 거부한다.

**지표.**

```text
WAPE = Σ|y − ŷ| / Σ|y|                              (분모 0 이면 오차도 0 일 때 0, 아니면 NaN)
MASE = MAE(모델) / 학습 구간의 주간 seasonal naive MAE (주기 168시간)
OCS  = (2 × 부족 대수 + 1 × 과잉 대수) / Σ|y|       (부족 비용 2, 과잉 비용 1)
```

**서빙.** 요청마다 피처를 다시 집계하면 83초가 걸려서, 136개 zone 의 다음 1시간 피처 행렬을 `serving_features.json` 스냅숏으로 미리 만들어 둔다. `GET /v2/model/forecast` 는 그 행렬에 승격 모델의 `predict` 를 실제로 실행해 zone 별 예측 출발 수를 내림차순으로 돌려주고, 응답에 run_id, artifact_id, mode, claim_status, freshness 를 붙인다.

## 3. 기상 피처 (NOAA, LLM 없음)

입력은 NOAA 일 단위 요약 JSON 이다. 센트럴파크 관측소(USW00094728) 하루에 한 행, 필드는 DATE, TMAX, TMIN, PRCP, SNOW, AWND. 2026년 상반기 181일치가 `data/fixtures/nyc_weather_2026h1.json` 에 있다.

변환은 `ml/forecasting/weather_lift.py` `_prev_day_features` 가 한다. 행의 현지 날짜에서 **하루 전** 날짜의 값을 가져온다. 그날 예보가 아니라 전날 관측값이라 미래 정보가 섞이지 않는다.

| 컬럼 | 값 |
|---|---|
| w_prev_tmax, w_prev_tmin | 전날 최고·최저 기온 (°F) |
| w_prev_prcp, w_prev_snow | 전날 강수량, 적설 (inch) |
| w_prev_awnd | 전날 평균 풍속 |
| w_prev_snow_flag | 전날 적설 > 0 이면 1 |
| w_prev_freeze_flag | 전날 최저 기온 < 32°F 이면 1 |
| w_prev_wet_flag | 전날 강수 > 0.1 inch 이면 1 |

전날 기록이 없으면 8개 모두 NaN 으로 두고 파이프라인의 중앙값 imputer 가 채운다. 결과는 개선이 아니었다. 1~5월 학습, 6월 210개 zone 평가에서 기본 피처만 쓴 WAPE 0.4868 이 기상을 더하면 0.4893 으로 0.51% 나빠졌고, 일 단위 블록 부트스트랩 95% 신뢰구간 [−0.0103, −0.0033] 도 0 아래였다(`reports/weather_lift.json`). 일 단위 기상은 시간 단위 수요 이력이 이미 담고 있는 정보였다.

## 4. 뉴스 이벤트 → LLM → 숫자 피처

### 4-1. 입력: 기사 한 건

기사는 JSONL 한 줄이다. article_id, title, text, source, published_at, first_seen_at, url_hash. 여기서 가장 중요한 필드는 두 시각이다.

```text
available_at = max(published_at, first_seen_at)
```

이 시각 이후의 예측에만 그 기사를 쓸 수 있다. 사건이 아무리 일찍 일어났어도 기사가 나오기 전에는 모델이 모르는 것으로 취급한다.

### 4-2. LLM 이 하는 일: 구조화만

`pipelines/events/anthropic_provider.py` 는 기사 한 건을 보내고 도구 호출 스키마로 다음을 받는다.

| 필드 | 허용값 |
|---|---|
| event_type | TRANSIT_DISRUPTION, WEATHER_SHOCK, LARGE_VENUE_EVENT, ROAD_CLOSURE, PUBLIC_GATHERING, SAFETY_INCIDENT, SYSTEM_ALERT, OTHER |
| demand_effect, capacity_effect | increase, decrease, unknown |
| severity, confidence | 0~1 실수 (범위 밖은 0~1 로 자름) |
| location_names | 지명 문자열 목록 |
| evidence_quotes | 기사 원문에서 그대로 복사한 인용문 |

시스템 프롬프트가 "수요가 몇 % 변할지는 절대 추정하지 말고 방향과 bounded 심각도만" 이라고 못 박는다. 인용문은 원문과 정확히 일치해야 하고, 하나도 일치하지 않으면 그 이벤트는 버린다. 지명은 LLM 의 문자열이 아니라 지명 사전(`config/places.py`)으로 좌표를 붙인다. 신뢰도 0.5 미만은 격리한다. 같은 유형에서 제목 토큰 Jaccard 0.6 이상이면 같은 사건으로 합친다. 결과는 Pydantic `EventExtraction` 으로 검증한 뒤에만 저장한다.

키가 없는 환경에서는 같은 인터페이스의 결정적 mock 제공자가 키워드 표(`config/events.py`)로 유형을 정하고 유형별 방향·심각도 prior 를 붙인다. 같은 입력이면 같은 출력이 나온다.

### 4-3. 숫자로 바꾸기, 경로 A: H3 zone 그래프 피처

`pipelines/features/graph_features.py` 는 예측 시각 t 를 cutoff 로 받아, accepted 이고 신뢰도 0.5 이상이고 `available_at ≤ t` 인 이벤트만 고른다. zone 중심에서 2 km 안의 이벤트 각각에 대해

```text
impact = severity × half_life_weight(t − available_at, 유형별 반감기) × exp_distance_decay(거리, 1 km)
```

를 계산한다. 반감기는 교통 중단 6시간, 날씨 12시간, 공연 4시간처럼 유형별로 다르다(`config/graph_features.py`). zone 하나의 피처는 이 값을 모아 만든다.

| 패널 컬럼 | 원천 |
|---|---|
| article_count_6h, article_count_24h (B2) | 6시간·24시간 안 이벤트 개수 (유형별 카운트 합) |
| event_severity_sum (B3) | severity × 출처 가중 × 시간 감쇠 의 합 |
| event_confidence_mean (B3) | 가용 이벤트 신뢰도 평균 |
| transit_disruption_flag (B3) | 6시간 안 교통 중단 이벤트가 있으면 1 |
| graph_distance_decayed_impact (B4) | impact 합 |
| graph_neighbor_zone_impact (B4) | 이웃 zone 1홉의 impact 합 × 0.5 |
| graph_transit_exposure (B4) | 교통 중단 이벤트의 impact 합 |

`dataset.py` `_fill_event_columns` 는 패널의 모든 시간에 대해 이 계산을 그 시간을 cutoff 로 다시 돌려 채운다. 14시 1분에 공개된 기사는 14시 행에 0 으로 들어가고, 이 사실은 회귀 테스트로 고정돼 있다. 영향 방향(demand_effect)은 이 경로에서 숫자로 쓰이지 않는다.

### 4-4. 숫자로 바꾸기, 경로 B: borough × 시간 피처

실제 LLM 추출 결과(`data/fixtures/news_live/claude_events_2026h1.jsonl`, 23건)는 이벤트마다 날짜, 유형, 심각도, boroughs 목록을 담고 있다. `ml/forecasting/llm_value_borough.py` 는 이를 네 컬럼으로 바꾼다. 실제 예 하나를 따라가면 이렇다.

```text
기사: "Thousands of Knicks fans celebrate big win with joyous New York parade"
      published_at = first_seen_at = 2026-06-18 16:38 UTC → available_at 12:38 EDT
LLM:  event_type PUBLIC_GATHERING, boroughs ["Manhattan"], severity 0.7
변환: Manhattan 의 12시부터 24시간 셀 각각에
      news_llm_active   += 1      (이벤트 개수)
      news_llm_severity += 0.7    (심각도 합)
      news_llm_crowd     = 1      (공연·집회 유형)
      news_llm_transit   = 0      (교통 유형 아님)
      Brooklyn 등 다른 borough 는 전부 0
```

같은 셀에 이벤트가 겹치면 개수와 심각도가 더해진다. 지역 규칙은 셋이다. 기사에 borough 이름이 있으면 그곳만, 이름이 없고 지하철·폭설 같은 전역 단서가 있거나 LLM 이 5개를 지정하면 전부, 둘 다 없으면 버린다. 추측해서 어딘가에 넣지 않는다.

### 4-5. 모델 입력 행과 결과

borough 실험의 한 행은 기본 피처 32개 + 허가 이벤트 4개(ev_active, ev_closure, ev_crowd, ev_upcoming6h, 시청 허가 DB 에서 시작·종료 시각으로 펼친 개수) + 뉴스 4개로 구성되고, 타깃은 그 borough 의 그 시간 출발 수다. 허가 이벤트까지 쓴 모델과 뉴스까지 쓴 모델을 같은 HGB 로 학습해 오차를 비교한다.

결과는 조건부였다(`reports/v2/llm_value/news_feature_conditions.json`, 시드 10개 앙상블, 일 단위 블록 부트스트랩).

| 창 | 이벤트당 평균 borough 수 | 전역 이벤트 비율 | 뉴스 피처 추가 시 오차 변화 |
|---|---:|---:|---:|
| 2월 | 4.2 | 80% | −0.96대 |
| 3월 | 3.67 | 67% | −0.86대 |
| 5월 | 2.29 | 29% | −0.76대 |
| 6월 | 2.0 | 25% | +1.24대 (상대 0.69%, CI [0.83, 1.64]) |

전역으로 켜진 피처는 다섯 borough 가 동시에 같은 값이 되어 공간 대비가 없고, 달력 피처와 겹친다. 지역이 특정된 이벤트가 많은 6월에만 개선이 나왔다. 영향 방향을 −1~+1 로 받아 심각도와 곱한 변형도 시험했지만 WAPE 0.0883 → 0.0906 으로 나빠져 채택하지 않았다.

## 5. 한눈에 보기

| 소스 | 변환 주체 | 모델 입력 컬럼 | 승격 모델 포함 | 측정 결과 |
|---|---|---|---|---|
| Citi Bike 트립 | 집계 + 지연/롤링 코드 | 기본 32개 | 포함 | WAPE 0.4974 (naive 0.688) |
| NOAA 일 단위 기상 | 전날 값 시프트 코드 | w_prev_* 8개 | 미포함 | −0.51% (악화) |
| NYC 허가 이벤트 | 시작·종료 시각 펼치기 | ev_* 4개 | 미포함 | 5월 단일 창 유의, 6창 재현 실패 |
| 뉴스 | LLM 구조화 → 코드 변환 | zone: 8개 / borough: 4개 | 미포함 | 지역 한정 이벤트에서만 +1.24대 |

LLM 은 숫자를 만들지 않는다. 기사에서 유형, 지역, 심각도, 근거를 뽑는 데까지만 쓰이고, 그 뒤의 시간 감쇠, 거리 감쇠, 셀 집계는 전부 설정값이 있는 코드가 한다. 그래서 같은 기사와 같은 설정이면 같은 피처가 나오고, 피처 하나를 어느 기사의 어느 문장에서 왔는지 되짚을 수 있다.

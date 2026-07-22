# V2 LLM Incremental Value Ablation (V2-03)

V2의 핵심 질문: **LLM** event 레이어가 자체 비용을 제하고도 단순 **rule** 레이어보다 가치를 더하는가?
이를 위해서는 세 개의 feature arm을 깔끔하게 분리하고 net-of-cost lift를 보고해야 한다.

> **Status: implemented + run (V2-03). Honest null.** Runner `ml/forecasting/llm_value.py`
> (`make v2-llm-value`). 실제 JC Citi Bike 2026 H1 + 실제 GDELT NYC 2026 news (371 articles)에서
> 세 arm은 **통계적으로 동일**하다 (ΔWAPE = 0, 95% CI [0,0]); test window의 event coverage는
> 0.306%이고 `arms_identical_on_test = true`이므로, verdict는
> **`insufficient_event_overlap`** (`claim_status: blocked_data`). LLM actual cost $0 (mock),
> estimated real $0.0061; **net LLM value −$0.01**. 이는 v1의 gap을 전체 3-arm + CI + profit + cost
> 프레임워크로 엄밀하게 확인한 것으로 — 조작된 positive가 아니라 유효하고 정직한 결과다.
> 전체 result + unblock path: `reports/v2/llm_value/`.
>
> **Borough re-measurement (NYC) — the FAIR test (`make v2-llm-value-borough`).** 입력을 바로잡았다:
> 5-month training (Jan–Apr, ~19.9M NYC trips), citywide news attribution (4→35 articles), 그리고
> **May**에 대한 test (June의 test window에는 attributable news가 0이었고, May는 216 news rows를 가진다).
> Arms A0 / A1 (+permitted structured feed) / A2 (+LLM news). **Result:** A1−A0 =
> **measured_improvement** (WAPE 0.1069→0.1047, CI [1.87, 5.88], +$33k) — structured events가 도움이 된다;
> A2−A1 = **negative_lift** (WAPE 0.1047→0.1075, CI [−6.02, −3.71], **net LLM value −$23,730**) —
> LLM-from-news 레이어는 공정한 test를 주어도 forecast를 *악화*시키고 비용까지 든다.
> **V2 answer (this data): structured event feed = worth money; LLM-from-news = net-negative.**
> Caveat: borough event effect는 작고 (~0.002 WAPE) sample에 민감하다. Artifact:
> `reports/v2/llm_value/incremental_value_borough.json`.
>
> **Real-LLM extraction — decisive test.** "mock keyword extractor가 나쁘다"는 confound를 제거하기 위해,
> claude-opus-4-8 (this session)이 371 articles를 모두 읽고 깨끗하고 근거 있는 NYC event set을 생성했다
> (`data/fixtures/news_live/claude_events_2026h1.jsonl`, 23 events: LIRR strike, NYC flash floods,
> concerts/festivals, blizzard travel bans — off-topic/false-positive 항목은 rejected). Re-run
> (`make v2-llm-value-borough --claude-events ...`, test May, 336 clean news-signal rows): A1−A0
> **measured_improvement** (WAPE 0.0908→0.0883, CI [1.08,6.71]); A2−A1 **여전히 negative_lift**
> (WAPE 0.0883→0.0905, CI [−5.32,−1.56], net LLM value −$17,789). **실제의 고품질 LLM extraction조차도**
> dense structured permitted feed에 비해 news events를 net-positive로 만들지 못한다 — news events는
> sparse하고, temporally coarse하며, official schedule과 redundant하다. 이 negative는
> extraction-quality artifact가 아니다.

## The decision metric — LLM Feature Value (LFV)

위 문단들은 A2−A1 비교를 prose + CI로 보고한다. V2는 또한
*"LLM features가 forecast accuracy를 의미 있게 개선했는가?"* 라는 질문을 **하나의 decision-grade metric**으로
공식화한다 (`ml/forecasting/llm_feature_value.py`, artifact에 `llm_feature_value_metric`으로 emit됨):

```text
skill = (WAPE_without_LLM − WAPE_with_LLM) / WAPE_without_LLM      # + = error reduced
```

- **LLM-active subset에서 측정**되며, 전역이 아니다. LLM features는 거의 모든 zone-hour에서 0이므로,
  global skill은 0 쪽으로 희석되어 효과를 감춘다. subset은 feature가 *on*인 것으로 정의되며 (결코 outcome으로가 아니라),
  따라서 유리한 row를 cherry-pick할 수 없다 — 이는 CLAUDE.md의
  "event-window WAPE" 원칙을 LLM-active window에 적용한 것이다.
- **Decision needs BOTH effect size and significance:** `MEANINGFUL_*`은 `|skill| ≥ 1%`
  (사전 선언된 `rel_threshold`) **그리고** paired per-row abs-error gain에 대한 day-block bootstrap CI가
  0을 배제할 때만 부여된다. 그렇지 않으면 `NO_MEANINGFUL_EFFECT`; `< 100` active zone-hours ⇒ `INSUFFICIENT_SUPPORT`
  (`blocked_data`, verdict를 조작하지 않음). A2−A1 test와 동일한 leakage-safe block bootstrap.

| decision | meaning |
|---|---|
| `MEANINGFUL_POSITIVE` | LLM features cut error on active zone-hours, CI-significant |
| `MEANINGFUL_NEGATIVE` | LLM features raised error on active zone-hours, CI-significant |
| `NO_MEANINGFUL_EFFECT` | effect below threshold or CI covers 0 |
| `INSUFFICIENT_SUPPORT` | too few active zone-hours to decide |

> **Measured result (test May, Claude-extracted events, Jan–Apr train / 10,655 rows):**
> **`MEANINGFUL_NEGATIVE`** — **336**개의 LLM-active zone-hours에서 LLM features가 WAPE를
> **5.52%** 만큼 **높인다** (skill −0.0552), paired abs-error gain에 대한 bootstrap CI는 **[−17.51, −0.98]로 0을 배제**.
> *global* A2−A1 mean gain (−3.53)도 significant하지만, metric의 active-subset 초점이
> verdict를 더 선명하고 희석되지 않게 만든다 (global skill은 −2.5%에 불과). **따라서 정량화된 답은:
> LLM news features를 추가해도 demand-forecast accuracy가 개선되지 않는다 — features가 발동하는 곳에서
> 측정 가능하게 악화시킨다.** negative net LLM value (−$17,789)와 일관됨. Artifact field:
> `incremental_value_borough.json#llm_feature_value_metric`.

core는 pure function으로, synthetic positive/negative/null/insufficient 케이스에 대해 unit-test되어 있어
(`tests/unit/test_llm_feature_value.py`), decision logic이 trip pipeline 없이도 검증 가능하다.

### Feature improvement + graph contribution (`make`-able: `ml/forecasting/llm_graph_value.py`)

−5.52%는 *feature engineering*이 문제임을 말해줬다 (publish time에 anchor된 flat 24h box,
citywide smear). 개선된 builder (`ml/forecasting/event_features_v2.py`)가 이를 고친다:
**event date + type-specific peak hour**에 anchor, **half-life decay**로 shaping (flat이 아닌 peaked),
**availability로 gate** (leakage-safe), **type별로 borough를 scope** (venue/gathering/safety = named
only; weather/transit/system은 citywide 가능), bounded severity. 별도의 **graph** arm은
borough-centroid distance decay를 통해 neighbor spillover를 추가한다. Arms A0 → A1(permitted) → A2(improved direct,
no graph) → A3(+graph); 실제 NYC demand로 측정 (test May, 10,655-row train, 336→ split into 194
direct-active / 222 graph-active zone-hours):

| comparison | decision | active skill | CI95 |
|---|---|---|---|
| **improved LLM feature** (A2 − A1) | `NO_MEANINGFUL_EFFECT` | −0.4% | [−4.90, 1.36] |
| **graph contribution** (A3 − A2) | `NO_MEANINGFUL_EFFECT` | −1.32% | [−3.76, 0.72] |

**Honest reading:**
- 개선은 **harm을 제거**했다: LLM feature는 `MEANINGFUL_NEGATIVE −5.52%` (old
  flat-box)에서 `NO_MEANINGFUL_EFFECT −0.4%` (이제 CI가 0을 걸침)로 이동했다. 더 나은 feature engineering ⇒ 더 이상
  forecast를 악화시키지 않는다 — 하지만 이제 **positive가 아니라 neutral**이다.
- 이 test에서 **graph contribution은 입증되지 않았다**: `NO_MEANINGFUL_EFFECT`, CI가 0을 걸침 (point
  estimate는 약간 negative). 여기서 graph가 도움이 된다고 **주장하지 않는다**.
- **왜 borough grain이 graph에 불리한가 (변명이 아닌 진짜 caveat):** 단 5개 borough로는
  graph가 추가하는 spatial-spillover 메커니즘이 coarse하고 (centroids 8–20 km 떨어짐), dense
  structured permitted feed (A1, 2,600 active rows)가 이미 실제 shock을 포착한다. graph의
  neighbor-propagation 가치는 **fine H3-zone grain** (수백 개의 인접 hex)을 위해 설계되었으며,
  그것이 graph-vs-no-graph 주장의 공정한 무대다. 그 test는 아직 실행되지 않았다.

Artifact: `reports/v2/llm_value/graph_contribution.json`.

### "News → permit-DB" reconstruction — hypothesis REFUTED (`ml/forecasting/llm_permitize_value.py`)

Tested hypothesis: permit feed는 정밀한 structured DB (exact time + exact
borough, 사전에 알려짐)이기 때문에 작동한다; 그러므로 LLM이 news를 그 **동일한 permit schema**로 re-extract하면,
structured 버전은 raw news가 못하는 곳에서 도움이 되어야 한다. 나는 (in-session) 23개 news events를 모두
permit-quality records로 재구성했다 — 정밀한 `event_start_at`/`event_end_at` + article로부터 추론한 특정 borough
(`claude_events_permitized_2026h1.jsonl`) — availability-gated.

| arm | WAPE |
|---|---|
| A1 (permit feed) | 0.0883 |
| A2 news **raw** (coarse) | 0.0883 |
| A2 news **permitized** (precise time + borough) | **0.0940** |

| comparison | decision | active skill | CI95 |
|---|---|---|---|
| permitized − A1 | `MEANINGFUL_NEGATIVE` | **−6.31%** | [−25.2, −5.5] |
| permitized − raw news | `MEANINGFUL_NEGATIVE` | **−6.30%** | [−22.7, −5.8] |

**가설은 반박되었다: news events에 permit-quality 정밀도를 부여하니 forecast가 *더 나빠졌다*,
좋아지지 않았다 — vague raw news보다도 더 나쁘다.** 두 가지 정직한 메커니즘:

1. **Sparse + confident = confident noise.** Raw news features는 vague하고 diffuse해서 tree가
   대부분 무시했다 (≈0 effect). Permitized features는 sharp하고 confident하다 (특정 borough의
   precise interval에 걸쳐 weight 1.0), 그래서 tree가 그것을 *신뢰*하고 조정한다 — 하지만 ~19개
   news events의 실제 demand effect는 heterogeneous하고 그렇게 적은 예제로는 학습 불가능하다 (transit
   strike는 substitution을 통해 bike demand를 *높일* 수도 *낮출* 수도 있다; festival은 locally 높인다), 그래서
   confident feature는 잘못되고 high-variance인 조정을 주입한다. 정밀도가 harm을 증폭한다.
2. **permit feed의 가치는 density이지 per-event structure가 아니다.** A1이 작동하는 이유는
   **63,070**개의 events를 담고 있기 때문이다 — model이 안정적인 "permitted-event → demand" coefficient를
   학습하기에 충분하다. News는 ~19개를 공급한다. 어떤 per-event 정밀도도 그렇게 작은 sample을 고치지 못한다.

3. **Timing gap (reported, not hidden):** 23개 events 중 4개가 `leakage_dropped` — show가 publication보다
   앞선 retrospective reviews로, forecast에 전혀 정보를 줄 수 없다. Permits는 사전에 filed되고;
   news는 coincident-or-after다.

**Conclusion:** permit feed가 제공하고 news가 결여한 것은 *구조*가 *아니다* — 그것은 events의
**volume과 consistency**다. Sparse news를 permit schema로 재구성해도 그것을 회복할 수 없으며,
여기서는 오히려 적극적으로 해를 끼쳤다. Faked가 아닌 정직한 negative result. Artifact:
`reports/v2/llm_value/permitize_contribution.json`.

### (a) News as an IMPORTANCE WEIGHT on the dense permit feed — also negative (`llm_importance_weight_value.py`)

Density 발견에 대한 follow-up: dense permit signal (63,070 events)을 유지하고 news가
그것을 *modulate*만 하도록 한다 — permit features가 news-importance scalar에 의해 증폭되며, news가
없는 곳에서는 손대지 않는다. Model에 들어가는 feature:

```
news_salience[b,h] = news importance in the borough-hour (severity x half-life decay, gated); 0 if none
ev_active_newswt   = ev_active * (1 + news_salience)
ev_crowd_newswt    = ev_crowd  * (1 + news_salience)
```

실제로 model에 공급된 예시 값 (from the run):

| borough-hour | ev_active | news_salience | ev_active_newswt |
|---|---|---|---|
| Manhattan 2026-01-24 19 | 63 | 0.90 | **119.70** |
| Queens 2026-01-24 19 | 14 | 0.90 | 26.60 |
| *(any borough-hour with no news)* | k | 0.00 | k×1.0 = k (unchanged) |

| comparison | decision | active skill | CI95 |
|---|---|---|---|
| importance-weighted − A1 | `MEANINGFUL_NEGATIVE` | **−7.82%** | [−25.6, −5.9] (WAPE 0.0883→0.0925) |

**역시 negative — 그리고 예시 row가 정확히 그 이유를 보여준다.** 가장 큰 salience 셀은 *Winter
Storm Fern* (2026-01-24, severity 0.9)이다: storm이 "newsworthy"하기 때문에 weight가 permit activity를
63 → 119.7로 *증폭*한다. 하지만 blizzard는 bike demand를 **억제**한다 — 그래서 "newsworthy"는 잘못된
방향을 가리킨다. News salience는 "뭔가 큰 일이 일어나고 있다"는 signal이며 그 *demand와의 관계는
heterogeneous하고 종종 반대다* (storms depress, festivals lift), 그리고 mixed types에 걸친 ~191 rows로는
type별 sign을 학습하기에 턱없이 부족하다. 그래서 gentle multiplier로 쓰여도, news는
confident하고 잘못된 sign의 조정을 주입한다.

### (b) H3-grain graph contribution — blocked (no geocoded events)

graph를 위한 가장 공정한 무대 (neighbor propagation을 가진 fine H3 zones)는 **실제 데이터로 실행할 수 없다**:
`pipelines/features/graph_features.py`는 events를 `lat/lng`로 H3 zones에 배치하지만, 실제
permit과 news events는 **borough-tagged만** 되어 있다 (permits는 street *description* +
precinct number도 담지만 coordinates는 없다). Street/precinct text를 geocoding하려면 offline에 없는
external data가 필요하고, coordinates를 조작하는 것은 허용되지 않는다. 그래서 **위의 borough-grain graph test (null)가
실제 event data가 지원하는 가장 fine한 공정 test다.** Forced가 아닌 `blocked_data`로 기록됨.

### SIGNED LLM demand signal — direction from the LLM (`llm_signed_value.py`)

Importance-weight 실패는 그것이 *unsigned* (항상 amplify)였다는 점이며, 그래서 blizzard가 forecast를
위로 밀었다. Fix: LLM이 event당 **signed** `demand_effect ∈ [−1,+1]`를 emit하게 하고 (blizzard
−0.9, festival +0.5, LIRR shutdown **+0.6** via bike substitution) signed feature
`news_demand_signal = demand_effect × severity × decay`를 만든다. Model은 ~19개의 sparse events로부터
학습하는 대신 *LLM의 reasoning에서* direction을 얻는다 (`claude_events_signed_2026h1.jsonl`).

| | value |
|---|---|
| **LLM sign-correctness** (agrees with actual demand deviation vs same-hour-last-week, 191 cells) | **0.77** |
| WAPE: A1 → +signed | 0.0883 → 0.0906 |
| signed − A1 | **`NO_MEANINGFUL_EFFECT`** −2.04%, CI [−7.26, +1.44] |

**이것이 핵심 결과다. LLM의 direction은 진짜로 옳지만 (0.77 agreement) — sign을 고치니
−7.82%의 *harm*이 −2.04%의 *neutral*로 바뀌었다 — 여전히 forecast를 개선하지 못한다.**
그 이유는 redundancy다: blizzard가 demand를 억제하고 있을 때, autoregressive features
(`dep_lag_1`, `dep_lag_24`, `dep_roll_mean_24`)는 **이미 demand가 낮다는 것을 보여준다** — model은 이미 그 effect를
*보고 있다*. "demand is down now"라고 말하는 signed news signal은 진행 중인 events에 대해서는
대체로 **demand history와 redundant**하다. News는 오직 예상치 못한 shock의 *sudden onset*에서만
(lags가 따라잡기 전에) 가치를 더할 수 있다 — 드물고, 여기서는 coarse timing +
availability gate에 의해 무뎌진다.

### Post-processing correction with per-mechanism factors — also negative (`llm_postprocess_value.py`)

실무자들은 종종 forecast를 input이 아니라 model *이후*에 보정한다. 그래서 feature 대신
`pred_corrected = pred_base + Σ_channel α_channel · signal_channel`를 적용하며, **mechanism별 separate
factor** (n-dimensional context: weather / gather / transit / safety)를 **train residuals에서 calibrate하고
out-of-sample로 test에 적용**한다.

| calibrated factor (fit on train) | value |
|---|---|
| α[weather] | +20.3 |
| α[gather] | **−470.6** |
| α[transit] | **−477.8** |
| α[safety] | +155.9 |

| | WAPE | verdict |
|---|---|---|
| A1 base | 0.0883 | — |
| A1 post-processed | 0.0899 | `MEANINGFUL_NEGATIVE` −21.36%, CI [−102.6, −4.95] |

**역시 negative — 그리고 fitted factors가 그 이유를 보여준다.** 크기가 **터무니없고** (−470, −477)
`gather`/`transit`는 **잘못된 sign**을 가진다 (positive surge signal이 거대한 *negative* 보정으로 곱해짐).
그것은 교과서적인 **calibration overfitting**이다: least-squares가 dev noise에 맞는 소수의 dev event-cells
(746, 소수의 events가 지배)에 큰 coefficients를 fit하고 test의 *다른* events에서 실패한다. Sparsity 문제가
단순히 "tree가 coefficient를 학습할 수 없다"에서 "post-processing calibration도 학습할 수 없다"로 옮겨갔을 뿐이다.
Fixed (unfitted) factor는 signed-feature arm과 같다 — neutral. 어느 쪽이든, ~19개 events로는 안정적인
event→demand factor를 고정할 수 없다.

### Forecast-horizon sweep — the "redundancy" rescue also fails (`llm_horizon_value.py`)

Redundancy 설명은 탈출구를 시사했다: 더 긴 horizon에서는 recent lags를 사용할 수 없으므로,
forward-looking event 지식이 더 중요해져야 한다. Horizon-legal features만으로 refitting하여 test했다
(lag_k는 k≥h일 때만 사용 가능; h>1에서는 rolling/momentum 없음):

| horizon | WAPE A0 → A1 → A2 | permit (A1−A0) | news (A2−A1) |
|---|---|---|---|
| 1h (nowcast) | 0.0908 → 0.0883 → 0.0906 | **+2.69% MEANINGFUL_POSITIVE** | −2.04% neutral |
| 6h / 24h | 0.1826 → 0.1824 → 0.1808 | −0.0% neutral | −9.59% neutral |
| 48h | 0.2187 → 0.2162 → 0.2145 | +1.09% neutral | −2.82% neutral |

**Not supported.** Event value는 horizon에 따라 *커지지 않는다*. Recent lags를 제거하면 baseline WAPE가
대략 *두 배*가 되고 (0.09→0.18→0.22), 이는 noise를 넓혀 permit signal의 significance를 **약화**시킨다
(nowcast에서만 `MEANINGFUL_POSITIVE`) — 강화하지 않는다.
News는 모든 horizon에서 neutral-to-negative로 남는다. 그래서 이 null은 더 긴 horizon이 고칠
nowcasting artifact가 아니다.

### Overall V2-03 finding (consistent across every attempt)

여섯 번의 시도 — extraction 개선, graph propagation 추가, permit schema로 재구성, news importance로
permit feed 재가중, **signed** LLM demand direction, per-mechanism factors를 가진 **post-processing**
보정 — 은 **모두 neutral-to-negative다.** 이야기는 단계마다 조여졌다:

1. Raw / improved news feature → neutral-to-negative (coarse, sparse).
2. Permit-schema reconstruction → negative (sparse + confident = confident noise).
3. Unsigned importance weight → negative (blizzard가 demand를 *잘못된 방향으로* 증폭).
4. **Signed** demand direction → LLM의 sign은 **77% 옳고**, harm은 제거되었지만 **여전히 개선 없음** —
   autoregressive demand history가 진행 중인 event의 effect를 이미 encode하기 때문이다;
   news signal은 lags와 **redundant**하다.
5. **Post-processing** 보정 (per-mechanism factors, train에서 calibrate) → negative; fitted
   factors가 터무니없고/잘못된 sign (−470) — sparse calibration이 **overfit**하고 test에서 실패한다.

6. **Horizon sweep** → event value는 lead time에 따라 커지지 않는다; null은 nowcasting artifact가 아니다.

**Conclusion:** LLM-from-news는 이 데이터에서 demand forecasting을 개선하지 않으며, 우리는 이제
그 *이유*를 세 층위에서 이해한다 — (a) **sparsity** (~19개 events로는 magnitude/factor를 가르칠 수 없다,
model coefficient든 post-processing calibration이든), (b) **sign heterogeneity** (77% 옳은
signed LLM effect로 해결됨), (c) autoregressive demand history와의 **redundancy**
(그리고 더 긴 horizon에서도 구제되지 않음). News는 오직 lags가 반응하기 전 *예상치 못한*
shock의 sudden onset에서만 도움이 될 것이다 — 드물고, 여기서는 coarse timing과
availability gate에 의해 제한된다. 이것은 단순히 관찰된 것이 아니라 이해된 negative result다.

### Is it really sparsity? Density learning curve + quality ablation (`llm_density_curve.py`, `llm_quality_ablation.py`)

"Sparsity"는 입증된 것이 아니라 주장된 것이었다 — 그리고 news는 permits와 세 개의 confounded axes
(density, precision, forward timing)에서 다르다. 두 개의 controlled ablations가 원인을 분리한다.

**Density curve** — precision + timing을 permit quality로 유지한 채 dense permit feed를 news-scale
counts로 subsample:

| N permit events | permit A1−A0 |
|---|---|
| 20 / 50 / 100 | INSUFFICIENT / neutral / neutral |
| 300 | **+2.03% MEANINGFUL_POSITIVE** |
| 1000 / 3000 / 10000 | neutral (non-monotonic) |
| 63,070 (all) | **+2.69% MEANINGFUL_POSITIVE** |

두 가지 사실: (1) **news scale (≤100 events; news는 ~19개)에서는 가치가 없다** → density가
*필요*하며, 19는 구조적으로 dead zone에 있다. (2) curve는 **non-monotonic**하다 (single random subsample에서
300에서 가치, 1000–10000에서 사라짐, full에서 다시) → raw count는 *충분하지 않다*;
어떤 events를 가지느냐가 중요하다 — low-relevance permits로 희석하면 count feature가 씻겨나간다.
그래서 "그냥 news를 더 모아라"로는 안정적으로 고칠 수 없다: 단지 더 많은 rows가 아니라
충분한 *demand-relevant* events가 필요하다.

**Quality ablation** — density를 FULL로 유지하고 한 axis를 news-like로 degrade:

| mode | what's degraded | permit A1−A0 |
|---|---|---|
| **full** | nothing (control) | **+2.69% MEANINGFUL_POSITIVE** |
| coarse_time | exact hour → flat over the day | **−0.33% collapses** |
| citywide | exact borough → all boroughs | **+0.53% collapses** |
| retro | advance → known only after onset | **+1.01% collapses** |

**모든 quality degradation이 가치를 non-significant로 붕괴시킨다.** 그래서 precise time, precise
location, forward-looking timing이 각각 *필요*하다 — 어느 하나라도 제거하면 permit feed가 도움을 멈춘다.

**입증된 원인은 안이한 "sparsity"가 아니라 네 속성의 conjunction이다:** permit feed가 작동하는 이유는
그것이 (1) **dense** (≥ 수백 개의 demand-relevant events), (2) **precisely timed** (exact
hour), (3) **precisely located** (exact borough), (4) **forward-looking** (event 이전에 알려짐)이기 때문이다.
News는 **네 가지 모두에서** 실패한다: ~19개 events (density threshold 아래),
day-and-borough-level coarse (time + location 실패), retrospective (timing 실패). 결정적으로, **"news를 더 모아라"는
axis (1)만 다룰 뿐이다; news는 여전히 (2)–(4)에서 실패할 텐데, coarse하고 사후적인 reporting이
바로 news의 구조적 본질이기 때문이다.** 그것이 진짜 답이다 — null은 news의 구조적
속성에 의해 over-determine되며, volume만으로는 고칠 수 없다.

### Can news even *satisfy* the four conditions? (`news_condition_audit.py`)

솔깃한 다음 단계: "news가 네 조건을 충족하도록 4-D feature vector를 encode하라." 하지만
조건들은 **source**의 속성 (어떤 정보가 존재하는가)이지 encoding의 속성이 아니다 — extractor는
명시되지 않은 hour를 발명하거나 retrospective review를 forward-looking으로 만들 수 없다. 23개 events를
source-checkable한 두 axes에 대해 audit하면:

| condition | news events satisfying |
|---|---|
| forward-looking (published >3h before onset) | **2 / 23** |
| precise single-borough | 12 / 23 |
| **BOTH forward AND precise** | **1 / 23** (and it is June — outside the May test window) |

Qualifying subset은 **~비어 있다 (1/23)**, 23개 news 항목 중 21개가 **coincident-or-retrospective**이기 때문이다
(lead time ≤ 0 — news는 events를 일어나는 *와중/후에* 보도한다; density도 ~19에 불과). 4-D vector나
reliability-weighted post-correction은 *원리상* 타당하지만, 1/23 reliable subset으로는
아무것도 아닌 것으로 줄어든다. 이것은 encoding이나 더 많은 volume으로 고칠 수 없다: forward-looking하고 precise한 events는
retrospective news가 아니라 **schedules / permits / announcements**에서 나온다. 그러므로 LLM
demand contribution으로 가는 정직한 경로는 LLM이 **forward-looking event source**를 A1 slot으로
structure하게 하는 것이다 — 그것이 존재할 때 (permit feed) 이미 +2.69% / +$33k를 전달한다.

### Synthetic ceiling — the post-correction DOES work when conditions are met (`llm_synthetic_ceiling.py`, `claim_status: simulated`)

post-correction이 *가능함*을 입증하기 위해 (real-news 가치를 주장하기 위해서가 아니라), 공개된 simulation:
KNOWN forward-looking, precise, dense event shocks (surge ×1.3–1.7 / suppress ×0.5–0.8)를
real demand에 주입한다; "LLM" signal은 sign + coarse magnitude만 안다; correction factor α는 train에서 fit되어
test에 적용된다. **이것은 `simulated`/`research`로 완전히 공개된 것이며 — real-news 결과가 아니고 business claim도 없다.**

| synthetic source | WAPE base → +feature → +post-corr | feature vs base | post-correction vs base |
|---|---|---|---|
| **dense + forward + precise** (1372 event-cells) | 0.1106 → 0.1042 → 0.1081 | **+20.86% MEANINGFUL_POS** | **+10.43% MEANINGFUL_POS** (CI [17.6, 108.7]) |
| sparse (news-scale, 157 cells) | 0.0953 → 0.0958 → 0.0956 | INSUFFICIENT_SUPPORT | INSUFFICIENT_SUPPORT |

**두 가지 정직한 결론:**
1. **LLM post-correction은 진짜로 forecast를 개선한다 (+10.43%, CI가 0을 배제) — event source가
   dense + precise + forward-looking일 때.** 그래서 real-news null은 **source** 문제이며
   (news가 네 조건에 실패), pipeline/method의 한계가 *아니다*. Method는 건전하다.
2. **news-scale density에서는 *완벽한* events조차 아무것도 주지 못한다** (INSUFFICIENT_SUPPORT) —
   메커니즘 측면에서 density가 필요함을 재확인.

이것은 ablations와 loop를 닫는다: 조건 위반 (real news) → 가치 없음; 충족
(이 simulation, 그리고 +2.69%의 real permit feed) → 가치. LLM *demand* contribution으로 가는 정직한
real-world 경로는 LLM이 진정으로 forward-looking한 source (event
calendars / schedules / permits)를 A1 slot으로 structure하게 하는 것이다 — retrospective news에서
짜내는 것이 아니다.

### LLM structuring the real permit feed — priors HURT, facts should be learned (`llm_permit_enrich_value.py`)

선택된 경로 (A): permit feed는 이미 네 조건을 충족하므로, LLM에게 그 일을 준다 —
각 permit의 free-text type/name을 읽고 crude count를 enrich한다. **Attempt 1은 LLM의
demand DIRECTION을 부과했다** (parade +0.4, film/production −0.3, market +0.2)을 signed feature로:

| arm | WAPE |
|---|---|
| A0 | 0.0908 |
| A1 crude counts | **0.0883** (+2.69% vs A0) |
| A1 + LLM signed enrichment | **0.0914** (−3.39% vs crude, MEANINGFUL_NEGATIVE) |

**해가 됐다 — A0보다도 나쁘다.** 교훈은 V2 contract 자체의 규칙 ("the LLM does not
directly compute demand")을 확인한다: crude count가 작동하는 이유는 *그것이 agnostic이기 때문이다* — tree가
데이터로부터 각 상황의 demand response를 **학습한다**. **검증되지 않은 demand-direction prior**를 부과하면
그것을 추측으로 덮어쓰고, 그 추측이 틀리면 적극적으로 오도한다.

**Attempt 2가 그것을 고쳤다** — LLM이 FACTS만 structure한다 (`event_type`을 6개 bucket으로 분류:
surge / gather / openstreet / market / production / civic), sign 부과 없음, model이 각
bucket의 response를 학습:

| arm | WAPE | vs crude |
|---|---|---|
| A1 crude counts | 0.0883 | — |
| A1 + per-type buckets | 0.0899 | **−1.9% MEANINGFUL_NEGATIVE** |

**역시 negative.** 하나의 count를 여섯 개의 더 sparse한 bucket-counts로 분해하면 model에게 동일한 ~2,600개
event-active cells에서 fit할 6개의 coefficients를 주게 된다 → overfit; low-variance aggregate
count가 이미 유용한 "how much permit activity" signal을 포착한다. 어떤 per-type demand 차이든
이만큼의 events로 borough-hour grain에서 회복하기엔 너무 작거나 noisy하다.

**Finding for path (A):** 이 real forward-looking source에서, 단순 aggregate count를 넘어선 LLM
*semantic structuring*은 도움이 되지 않는다 — direction 부과 (−3.39%)도 factual type-splitting
(−1.9%)도. **Aggregate event count가 이 데이터/grain의 ceiling이다.** 더 fine한 LLM structure는
더 fine한 spatial grain (per-H3-zone, parade route가 localize되는 곳)이 필요하다 — 여기서는
permits가 borough-tagged (no coordinates)이기 때문에 blocked. 이것으로 demand 측면은 exhaustive하며;
추가 demand 실험은 fishing이 될 것이다.

### "How can more information reduce accuracy?" — train vs test diagnostic (`llm_overfit_diagnostic.py`)

직관은 옳다: 이상적인 learner에게 더 많은 features는 결코 해가 될 수 없다.
train-vs-test breakdown이 실제로 무슨 일이 일어나는지 보여준다 (그리고 우리의 첫 가설을
바로잡았다 — 그것은 classic overfitting이 **아니다**):

| arm | #feat | TRAIN WAPE | TEST WAPE |
|---|---|---|---|
| A0 demand+calendar | 32 | 0.0631 | 0.0908 |
| A1 crude aggregate count | 36 | **0.0485** | **0.0883** |
| A1 typed (6 buckets) | 40 | 0.0533 | 0.0899 |

두 가지 해석:
1. **더 많은 정보는 진짜로 도움이 된다** — A1 crude가 train (0.0485<0.0631)과 test
   (0.0883<0.0908) **양쪽에서** A0을 이긴다. permit signal 추가가 fit *과* generalization을 개선한다, 직관대로.
2. **Typed가 train AND test 양쪽에서 crude보다 나쁘다** — 그래서 overfitting이 아니다 (그렇다면
   train은 좋고 test는 나빠야 한다). 그것은 **representation dilution**이다: 여섯 개의 per-type buckets는
   aggregate count와 *동일한* 정보를 담지만 (그 합 ≈ count), 각 bucket은 대부분의
   active cells에서 ≈0이다. Capacity-limited greedy boosted tree (fixed leaves/iterations, early stopping)는
   여섯 개의 sparse features보다 **하나의 dense high-signal feature**를 더 잘 활용한다 — sparse columns의
   splits는 low-value이고 budget을 낭비하므로, training fit조차 degrade한다.

**그래서 "more information"은 결코 accuracy를 낮추지 않았다 — 더 sparse한 encoding의 *동일한* 정보가 낮췄다.**
infinite-data / infinite-capacity model은 tie를 이룰 것이다 (typed set은 count를 sum으로 포함);
손실은 finite-sample representation efficiency다. 실용적 교훈은 feature-engineering 교훈이다:
aggregate count가 더 나은 *encoding*이며, 더 fine한 LLM structure는 각 slice를 추정할 만큼
충분한 per-type event density (또는 더 fine한 spatial grain)가 있을 때만 값을 한다 — 이 데이터는 그것이 없다.

> **Synthesis:** "where and why LLM features matter" 요약은
> [`V2_WHY_LLM_FEATURES.md`](V2_WHY_LLM_FEATURES.md)에 있다.

### Insight — where the LLM adds value, and how to attribute the WAPE lift

**news**를 위한 demand-feature 경로는 exhausted되었다 — 하지만 그것이 thesis 전체였던 적은 없다. 두 개의
LLM/event contributions가 V2에서 **measured positives**다:

1. **structured event 레이어가 forecast를 개선한다.** permit feed는 nowcast에서
   `MEANINGFUL_POSITIVE +2.69%` (A1−A0)를 추가하고 ledger에서 **+$33k**를 추가한다 — 핵심
   "event-aware forecasting" 주장, measured. pipeline은 *event-source agnostic*이다:
   forward-looking하고 dense하며 geocoded된 LLM event stream이 정확히 동일한 A1 slot으로 들어갈 것이다. NYC의
   retrospective/sparse GDELT news는 단지 그 stream이 아닐 뿐이다.
2. **LLM은 structuring, routing, explanation에서 measured value를 더한다** — V2-06: real-LLM
   Copilot router는 keyword baseline의 0.75 대비 1.0/1.0/1.0을 기록하며, hallucinated answers를 3→0으로 줄인다.
   이곳이 addendum이 항상 LLM을 놓았던 자리다 ("event structuring, tool routing, explanation;
   the LLM does not directly compute demand").

그래서 V2 verdict는 "LLM은 쓸모없다"가 아니라: **LLM의 검증된 가치는
structuring/routing/explanation과 event 레이어를 구동하는 데 있으며, sparse retrospective news에서 추가
demand accuracy를 추출하는 데 있지 않다.**

**Attribution guardrail (for the portfolio).** measured WAPE lift는 **structured
event feed**에 속하지 LLM에 속하지 않는다. repo는 이미 이를 올바르게 명시한다 — headline lift
(`borough_event_lift.json`, WAPE −1.65% / V2 A1−A0 +2.69%)는 *event-feature* lift로 labeled되어 있고
NYC permit feed (no LLM)에서 오며, B0–B4 ablation은 **B3 (+LLM event features) = B1** (no
lift)임을 보여준다. 그래서 "LLM features improved WAPE" 형태의 어떤 주장도 **not supported**이며 다음과 같이 읽혀야 한다:

> *Structured event features improved WAPE (measured); LLM-from-news added no incremental forecast
> lift (verified across 7 approaches). The LLM's measured value is in GraphRAG grounding / routing /
> explanation (answer correctness 40%→100%, hallucinations 10/10→0), not in demand accuracy.*

LLM을 위한 남은 미실현 demand niche는 **unstructured *하고* forward-looking한** source다 —
event previews / press releases / venue announcements / community notices — LLM이 이를
A1 slot을 위한 permit-quality records로 structure할 것이다. Retrospective GDELT news는 그
source가 아니며 (2/23 forward-looking), 그래서 이 niche는 claimed가 아닌 untested (`blocked_data`)로 기록된다.

## Three arms (identical cutoffs/splits)

```text
A0  No-Event    : demand history + calendar only
A1  Rule-Event  : A0 + deterministic rule-based event features
                  (keyword/geo/time rules — no LLM)
A2  LLM-Event   : A0 + LLM-extracted + graph-propagated event features
```

세 arm 모두 동일한 seed로 **동일한** rolling H3 holdout windows (`V2_EVALUATION_PROTOCOL.md`)에서 실행된다.
Arms는 features에서만 다르다.

## What is measured

```text
predictive lift : metric(A1) - metric(A0)     (rule value)
                  metric(A2) - metric(A1)     (LLM incremental value over rule)
profit lift     : net(A2) - net(A1)           (via the ledger, V2-02)
LLM cost        : tokens, $ per run, amortized per decision
net LLM value   : profit lift - LLM cost
```

lift를 confidence interval과 함께 보고한다 (예: holdout windows에 대한 block-bootstrap). Rule과 LLM
arms는 conflate되지 않고 attributable해야 한다.

## Honesty requirements

- **A2가 A1을 이기지 못하면**, 그것을 명료하게 보고하고 이유를 분석한다 (event overlap, extraction
  quality, propagation). Null result는 유효하고 publishable한 V2 outcome이다.
- LLM incremental cost는 **항상** 포함된다 — 버는 것보다 더 드는 lift는 net-negative로 보고된다.
- "Model-attributed" 표현만; causal claim 없음.
- Overlap을 조작하기 위한 fabricated event content 없음 (base-contract invariant).

## Artifact schema — `reports/v2/llm_value/incremental_value.json`

```jsonc
{
  "run_id": "run_...",
  "arms": {
    "A0_no_event":   { "wape": null, "net": null },
    "A1_rule_event": { "wape": null, "net": null },
    "A2_llm_event":  { "wape": null, "net": null }
  },
  "lift": {
    "rule_over_none":  { "wape_delta": null, "ci": [null, null] },
    "llm_over_rule":   { "wape_delta": null, "ci": [null, null] },
    "profit_llm_over_rule": null
  },
  "llm_cost": { "tokens": null, "usd": null, "usd_per_decision": null },
  "net_llm_value": null,
  "claim_status": "pending"
}
```

## Acceptance

- 세 arm이 분리되고 config로부터 reproducible.
- 공유된 cutoffs/splits 검증됨.
- Cost 포함; net value 보고됨; null results 숨기지 않음.

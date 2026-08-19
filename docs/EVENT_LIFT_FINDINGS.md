# Do event-aware features improve demand forecasting? — measured findings

> ## 정정 (2026-08-19): 이 문서의 긍정적 결론은 철회되었습니다
>
> 아래 본문은 2026년 6월 홀드아웃에서 이벤트 피처가 WAPE를 1.65% 낮췄다고(0.1013 → 0.0996,
> CI [0.36, 5.11]) 보고합니다. **현재 저장소의 데이터로 같은 명령을 그대로 재실행하면 이 결과가
> 재현되지 않습니다.**
>
> | 항목 | 원본 artifact | 현재 데이터 재현 |
> |---|---|---|
> | train / test 행 | 14,759 / 3,366 | 13,630 / 2,881 |
> | 이벤트 없음 WAPE | 0.1013 | 0.0946 |
> | 이벤트 포함 WAPE | 0.0996 | 0.0964 |
> | 상대 변화 | **+1.65% 개선** | **-1.94% 악화** |
> | 95% CI | [0.36, 5.11] | **[-6.09, -0.86]** |
> | 판정 | measured_improvement | **negative_lift** |
>
> 재현 명령: `python -m ml.forecasting.borough_event_lift --data-dir <NYC 2026-01..06>
> --events data/fixtures/nyc_permitted_events_filtered.jsonl.gz --test-from 2026-06-01`
>
> ### 원인: Jersey City 트립이 Staten Island로 오배정되어 패널에 섞였습니다
>
> 행 수 차이(원본 18,125 vs 재현 16,511)를 추적한 결과, 원본은 **NYC 아카이브와 Jersey City
> 아카이브를 같은 디렉터리에 넣고** 실행한 것으로 확인됩니다.
>
> `stream_borough_cells`는 트립 좌표에서 **가장 가까운 borough 중심점**을 찾아 배정합니다.
> Jersey City(약 40.72, -74.04)는 허드슨강 건너 **뉴저지**인데, NYC 5개 중심점 중 가장 가까운 것이
> 유일하게 서쪽에 있는 **Staten Island(40.579, -74.15)**입니다. 그 결과 JC 트립이 통째로 Staten
> Island 수요로 기록됩니다.
>
> | 2026-06 borough별 시간 셀 | NYC만 | NYC + JC |
> |---|---|---|
> | Manhattan / Bronx / Brooklyn / Queens | 735 / 732 / 731 / 722 | 동일 |
> | **Staten Island** | **1** | **486** |
>
> 이 486이 원본과 재현의 6월 test 행 차이(3,366 - 2,881 = 485)와 일치합니다. 즉 원본 test set의
> 약 14%가 **뉴저지 수요에 "Staten Island" 라벨이 붙은 행**이었습니다.
>
> 문제는 여기서 그치지 않습니다. 이벤트 피처는 **NYC permitted events**에서 오므로, 그 행들은
> **뉴저지에서 발생한 수요에 실제 Staten Island의 행사 정보를 결합**한 것이 됩니다. 서로 인과관계가
> 없는 두 데이터가 같은 행에 묶여 있었습니다.
>
> 따라서 원본의 `+1.65%`는 이벤트 신호의 효과가 아니라 **데이터 오배정의 산물**로 보아야 합니다.
> 오배정된 행을 제거하면(NYC만 사용) 같은 6월 홀드아웃에서 -1.94% 악화가 나옵니다.
>
> 재현 결과는 독립적으로 수행한 rolling-origin 검증의 6월 창과 일치합니다(행 수 13,630 / 2,881 /
> 이벤트 2,612가 정확히 같고, mean_gain -3.42 vs -3.46). 즉 두 검증이 서로를 뒷받침합니다.
> 전체 경위는 `reports/v2/llm_value/rolling_origin_ablation.json`과 `docs/STATUS.md` 참고.
>
> 아래 본문은 **당시 기록으로 보존**합니다. 지우지 않는 편이 기록으로서 정확하기 때문이며,
> 현재 유효한 결론이 아닙니다. 날씨 피처에 대한 부정적 결론(개선 없음)은 그대로 유지됩니다.

This note records a real experiment, run end-to-end on real data, that asks the central product
question of ShockFlow AI in the plainest possible way: **if we add features derived from timestamped
real-world events to a demand-only forecaster, does the forecast actually get more accurate?** The
short answer is *yes for city events, no for June weather* — and both results are reported exactly as
they came out of the pipeline, with nothing tuned to flatter the claim.

All numbers below come from executed fits on real Citi Bike trips, real NYC permitted-event records,
and real NOAA weather. Nothing here is a placeholder or a simulation. The claim is deliberately
worded as *model-attributed* improvement, never *causal* — we measured that a model given event
features predicted June demand better, not that the events *caused* the demand in a counterfactual
sense.

## What we tested

The question was framed as a strict train/test split in time: **train on January–May 2026, hold out
all of June 2026 as the test set.** A model trained only on demand history and calendar features (the
"B1" baseline) is compared against the same model given a small set of extra event-derived features.
If the event features carry real predictive signal, the June error should drop by an amount that is
distinguishable from noise.

We ran this twice, with two different real event sources:

- **NYC permitted events** — parades, street fairs, block parties, farmers markets, filming, and
  street/sidewalk closures — which shift mobility in the specific place they happen.
- **NOAA daily weather** at Central Park — temperature, precipitation, snow, wind — which shifts
  demand city-wide when it swings.

## The data

- **Trips:** 20,337,044 real Citi Bike trips across the six months, downloaded from the public trip
  archive. Because full-city trips at the H3-zone grain are too large to hold in memory here, they
  are **streamed** file-by-file and aggregated on the fly.
- **Events:** the NYC Open Data permitted-events export (~1.5 GB raw) filtered down to the
  **63,070** genuinely mobility-relevant permits — street/sidewalk/plaza closures plus parades,
  street fairs, markets, filming and processions — after dropping the ~half of the file that is
  youth/adult sports permits with no bearing on bike demand.
- **Weather:** 181 daily records (Jan 1 – Jun 30) from NOAA station USW00094728 (Central Park):
  max/min temperature, precipitation, snowfall, average wind.

Provenance is preserved end to end, and the filtering step is a pure pass-through — no event record
was invented or altered, only included or excluded.

## How the measurement is kept honest

**Grain.** The event experiment aggregates demand to **borough × local hour** (five boroughs). This
is a deliberate, documented approximation: full-NYC H3-zone forecasting does not fit in this
environment, so each trip's start point is assigned to its nearest borough centroid. It is coarser
than the product's H3 grain, and boundary points near a river can be misassigned — but it lets the
event signal, which the permits already carry at borough level, be measured without any geocoding.

**No leakage.** Demand lag and rolling features come from the shared leakage-safe builder (the
current hour never enters its own lag; rolling windows are shifted). Event features use only the
**public permit schedule** — an event's borough and start/end time are published well before it
happens — so counting the events that are active or imminent at a forecast hour uses information that
was genuinely available at that hour. Weather features use the **previous day's** observed values, so
no future weather informs a past prediction. A random train/test split is never used; the split is a
single expanding-window holdout at the calendar boundary.

**An honest verdict, not a p-hack.** For each experiment the paired per-row improvement is
bootstrapped over **day blocks** (resampling whole days, so autocorrelation within a day does not
shrink the interval), giving a 95% confidence interval on the mean error reduction. A gain is only
called a *measured improvement* when that interval lies entirely above zero; otherwise the verdict is
`no_lift`, `negative_lift`, or `inconclusive`, and it is reported as such. The model is a single fast
gradient-boosted tree (`HistGradientBoostingRegressor`) fit once per feature set, chosen so a
multi-month panel stays tractable.

## What we found

### Event features help — measured improvement

On the June holdout, adding the four event features (active events, active street closures,
crowd-drawing events, and imminent events in the next six hours) reduced borough-hour forecast error
by a margin that is statistically distinguishable from zero:

| Model | WAPE | MAE |
| --- | --- | --- |
| B1 — demand + calendar | 0.1013 | 165.23 |
| **B1 + events** | **0.0996** | **162.50** |

- **WAPE fell 1.65%** in relative terms (0.1013 → 0.0996).
- Verdict: **`measured_improvement`** — mean per-row error reduction of **2.73**, with a 95%
  confidence interval of **[0.36, 5.11]**, entirely above zero, bootstrapped over 30 day-blocks.
- Of the 3,366 June test rows, 2,718 carried an event signal, so the effect is measured where events
  actually occur, not on a handful of edge cases.

In words: a forecaster that knows a parade or street closure is scheduled in a borough predicts that
borough's June bike demand measurably better than one that does not. This is the core ShockFlow AI
claim, validated on real data — modestly in size, but real and statistically supported.

### Does the event feature only push demand UP? — no, DOWN is where it wins

A natural question: does the event feature help only by predicting demand *increases* (a parade
draws riders), or does it also correctly pull the forecast *down*? We split the 3,366 June test rows
by the direction the event feature moved the forecast relative to the baseline
(`python -m ml.forecasting.lift_direction`; the aggregate MAE reconciles exactly with the headline —
165.23 → 162.50, +2.73/row).

| Direction the event feature moved the forecast | Rows | Improved accuracy | Mean error reduction |
| --- | --- | --- | --- |
| Pushed **UP** (pred > baseline) | 1,394 | 56.0% | +5.23 |
| Pushed **DOWN** (pred < baseline) | 1,832 | **62.0%** | +1.03 |
| ~No change | 140 | 53.6% | +0.02 |

- The feature moves the forecast **down more often than up** (1,832 vs 1,394 rows) — it is genuinely
  bidirectional, not a one-sided "event = more demand" bump. Street closures and capacity effects pull
  demand down, and the model learns that.
- Downward corrections are the **more reliable** direction: right 62% of the time vs 56% for upward.
- The single cleanest signal is exactly the case in the question — when actual demand came in **below**
  the baseline forecast *and* the event feature pushed the prediction down (1,193 rows): **95.2% of
  those rows improved, mean error reduction +17.4** rides per borough-hour. When a scheduled closure
  or capacity effect suppresses demand, the event-aware model catches the dip the baseline misses.

So yes — there are many measured cases where the event feature correctly predicts *lower* demand and
matches the outcome better; that is where most of the aggregate gain comes from.

### June weather does not help — an honest negative

The same experiment design applied to weather features (run on the smaller Jersey City H3-zone panel,
210 zones, 145k train / 40k test rows) came out the other way:

| Model | WAPE | MAE |
| --- | --- | --- |
| B1 — demand + calendar | 0.4868 | 1.318 |
| B1 + weather (prev-day) | 0.4893 | 1.325 |

- WAPE **rose 0.51%**; verdict **`negative_lift`**, CI **[-0.010, -0.003]**, entirely below zero.
- The most likely reason is the test month: June in New York is mild, with little day-to-day weather
  variance, so previous-day weather adds noise rather than signal — and the calendar features already
  capture the smooth seasonal shape. Weather would plausibly help on a winter holdout; on June it
  does not, and we report that rather than hide it.

The two results are not directly comparable in WAPE level — they run on different panels and grains
(NYC boroughs vs. Jersey City zones) — but each is a valid within-experiment baseline-vs-feature
comparison, which is what the lift claim rests on.

## Honest limitations

- **Borough grain, approximate geocoding.** The event result is at borough × hour with
  nearest-centroid assignment, coarser than the product's H3 zone grain. A finer result would need
  full-NYC H3-zone trip processing (out of reach in this environment) and event coordinates rather
  than borough labels.
- **Model-attributed, not causal.** We measured better prediction, not a causal effect.
- **One split, one test month.** A single June holdout; a rolling multi-month evaluation would
  strengthen the claim.
- **Modest effect size.** 1.65% WAPE is real (CI above zero) but small; it should be described as a
  measurable, honest lift, not a headline transformation.

## Reproduce

```bash
# 1) real trips (streamed; ~3 GB of NYC monthly archives)
python -m pipelines.collectors.download_citibike --from 202601 --to 202606

# 2) filter the raw NYC permitted-events dump to the demand-relevant subset
python scripts/filter_permitted_events.py <raw_events.json> \
    data/fixtures/nyc_permitted_events_filtered.jsonl.gz

# 3) event lift — borough grain, train Jan-May / test June
python -m ml.forecasting.borough_event_lift \
    --data-dir data/raw/citibike \
    --events data/fixtures/nyc_permitted_events_filtered.jsonl.gz \
    --test-from 2026-06-01
# -> reports/borough_event_lift.json

# 3b) directional breakdown — does the event feature also correctly predict DOWN?
python -m ml.forecasting.lift_direction   # reconciles with the headline; prints per-direction accuracy

# 4) weather lift (Jersey City panel), same split
python -m ml.forecasting.weather_lift \
    --data-dir data/raw/citibike \
    --weather data/fixtures/nyc_weather_2026h1.json \
    --test-from 2026-06-01
# -> reports/weather_lift.json
```

## Bottom line

Across everything measured on real data: the demand baseline beats a seasonal-naive reference; **event
features produce a small but statistically significant accuracy gain (WAPE −1.65%, CI above zero) on
held-out June demand**; June weather features do not help and we say so; and the event-aware pricing
work is measured separately (simulated) elsewhere. The headline product claim — that turning
timestamped events into features improves demand forecasting — is supported by a real, reproducible
measurement, stated with its true scope and limits.

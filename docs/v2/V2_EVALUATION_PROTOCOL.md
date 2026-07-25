# V2 Evaluation Protocol — H3 Multi-Holdout (V2-01)

`../EVALUATION_PROTOCOL.md`를 확장한다. V2는 단일 holdout 윈도우를 **rolling /
expanding multi-holdout**로 대체하여, lift가 운 좋은 하나의 split에서 나온 산물이 아니도록 한다.

> **Status: implemented + measured (V2-01).** Runner `ml/forecasting/h3_multiholdout.py`
> (`make v2-holdout`). 첫 measured run: 실제 Citi Bike **Jersey City** 2024년 3월–8월,
> 210,042 H3 zone×hour 행 / 234 zones, 3개의 월별 rolling 윈도우. 승격된 model
> `hist_gradient_boosting`; 집계 WAPE **0.4828 ± 0.0030**, MASE **0.7996** (B0 ~0.648을 능가).
> 전체 결과: `reports/v2/holdout/`. 범위: JC (NYC 전역이 아님), B1 features만 사용
> (events = V2-03), promotion pool은 `ridge` + `hist_gradient_boosting`로 한정 (`--algos all`
> 로 전체 zoo 사용 가능).

## Design

- **Grain:** H3 zone × local hour (`America/New_York`), targets `departures`, `arrivals`,
  `net_flow`.
- **Split:** rolling-origin (또는 expanding-window). **절대 random K-fold를 쓰지 않는다.**
- **Windows:** 연속된 holdout 윈도우 ≥3개; 각 윈도우는 명시적인 `train_end` (= forecast
  cutoff)와 `test_start/test_end`를 갖는다. 모든 경계 + seed를 기록한다.
- **Availability:** event 파생 features는 `available_at <= forecast_cutoff`를 따른다. Leakage
  regression test (14:01에 available해진 article은 14:00 cutoff에 기여하면 안 됨)가 통과해야 한다.
- **Arms share cutoffs:** 모든 ablation arm (`V2_LLM_VALUE_ABLATION.md` 참조)은 동일한
  윈도우/split을 사용한다.

## Metrics (윈도우별 + 집계)

```text
WAPE            (define zero-denominator behavior explicitly)
MAE
MASE            (against explicit seasonal-naive scale)
event-window WAPE
peak direction accuracy
forecast delta stability
```

윈도우별 값 **그리고** 집계값 (윈도우 전반의 mean ± spread)을 함께 보고한다. 전체 성능과
event-window 성능을 분리해 보고한다.

## Artifact schema — `reports/v2/holdout/h3_multiholdout.json`

```jsonc
{
  "run_id": "run_...",
  "model_version": "...",
  "feature_version": "...",
  "seed": 42,
  "split": "rolling_origin",
  "windows": [
    {
      "window_id": 0,
      "train_end": "2026-06-15T00:00:00-04:00",
      "test_start": "2026-06-15T00:00:00-04:00",
      "test_end": "2026-06-22T00:00:00-04:00",
      "metrics": { "wape": null, "mae": null, "mase": null,
                   "event_window_wape": null, "peak_dir_acc": null }
    }
  ],
  "aggregate": { "wape": null, "mae": null, "mase": null },
  "claim_status": "pending"
}
```

## Acceptance

- 윈도우 ≥3개, 경계 + seed 저장, random split 없음.
- Leakage tests green.
- 승격된 model = 비-demo 모드에서 served되는 model (`V2_MISSION.md`의 evidence #1).
- event-aware features가 baseline 대비 개선되지 않으면, **그대로 보고하고** 이유를 분석한다.

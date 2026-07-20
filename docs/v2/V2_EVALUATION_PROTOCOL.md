# V2 Evaluation Protocol — H3 Multi-Holdout (V2-01)

Extends `../EVALUATION_PROTOCOL.md`. V2 replaces the single holdout window with a **rolling /
expanding multi-holdout** so lift is not an artifact of one lucky split.

## Design

- **Grain:** H3 zone × local hour (`America/New_York`), targets `departures`, `arrivals`,
  `net_flow`.
- **Split:** rolling-origin (or expanding-window). **Never random K-fold.**
- **Windows:** ≥3 consecutive holdout windows; each has an explicit `train_end` (= forecast
  cutoff) and `test_start/test_end`. Record all boundaries + seed.
- **Availability:** event-derived features obey `available_at <= forecast_cutoff`. Leakage
  regression test (article available 14:01 must not contribute to a 14:00 cutoff) must pass.
- **Arms share cutoffs:** every ablation arm (see `V2_LLM_VALUE_ABLATION.md`) uses identical
  windows/splits.

## Metrics (per window + aggregated)

```text
WAPE            (define zero-denominator behavior explicitly)
MAE
MASE            (against explicit seasonal-naive scale)
event-window WAPE
peak direction accuracy
forecast delta stability
```

Report per-window values **and** an aggregate (mean ± spread across windows). Report overall and
event-window performance separately.

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

- ≥3 windows, boundaries + seed persisted, no random split.
- Leakage tests green.
- Promoted model = the one served in non-demo modes (evidence #1 in `V2_MISSION.md`).
- If event-aware features do not improve over baseline, **report it honestly** and analyze why.

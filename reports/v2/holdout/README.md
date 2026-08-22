# reports/v2/holdout/ — V2-01 H3 Multi-Holdout

**Measured** (2026-07-20). Reproduce: `make v2-holdout` (needs `data/raw/citibike/`; fetch with
`make download-citibike MONTHS="..."` or the `--jersey-city` downloader).

## Artifacts

- `h3_multiholdout.json` — per-window + aggregate metrics (schema in
  `docs/v2/V2_EVALUATION_PROTOCOL.md`). Carries the result envelope (`run_id`, `artifact_id`,
  `mode`, `claim_status=measured`, `freshness`).
- `promoted_model.json` — promoted-model manifest (algorithm, params, selection CV WAPE, training
  span). Read by `ml/forecasting/promoted.py` for serving in non-demo modes.
- `promoted_model.joblib` — fitted estimator (git-ignored, regenerable via `make v2-holdout`).

## Headline result (measured, real data)

- **Data:** real Citi Bike **Jersey City** trip history, Mar–Aug 2024 → 210,042 usable
  H3 zone×local-hour rows, 234 H3 zones (DST-aware). _Not NYC-wide — see the geography nuance in
  `reports/v2/final/v2_audit.md`._
- **Grain:** H3 zone × local hour (`America/New_York`). **Target:** `departures`.
- **Split:** rolling-origin, expanding window, 3 consecutive month-long test windows.
- **Promoted model:** `hist_gradient_boosting` (lr=0.05, max_depth=8, max_iter=600), selected by
  CV WAPE on the pre-first-window development span. Promotion pool: `ridge`,
  `hist_gradient_boosting` (bounded for tractability; `--algos all` runs the full zoo).
- **Features:** B1 (demand history + calendar) only. Event features (B2–B4) are **V2-03**.

| Window | Test month | n_test | WAPE | MAE | MASE | B0 seasonal-naive WAPE |
|---|---|---|---|---|---|---|
| W0 | 2024-06 | 38,246 | 0.4823 | 1.395 | 0.821 | 0.6435 |
| W1 | 2024-07 | 38,395 | 0.4794 | 1.398 | 0.801 | 0.6480 |
| W2 | 2024-08 | 37,438 | 0.4867 | 1.379 | 0.776 | 0.6521 |
| **Aggregate** | 3 windows | — | **0.4828 ± 0.0030** | — | **0.7996 ± 0.0186** | ~0.648 |

The promoted model beats the seasonal-naive baseline on every window (MASE < 1) and is stable
across windows (WAPE std 0.003). Metrics are from executed fits only; no fabrication.

# Evaluation Protocol — Phase 06 Forecasting

This document fixes the forecasting evaluation so a reviewer can reproduce every number from a
saved config (CLAUDE.md §11, §18). Metrics are generated only from executed experiments; if
event-aware features do not improve performance, the result is reported honestly (§11.4, §22).

## Task

- **Grain**: H3 zone × local hour (`America/New_York`), resolution 9 (§4).
- **Target**: `departures` (primary). The model predicts the current hour's demand from
  information available at the start of that hour — lags ≤ t−1 and the calendar of hour t —
  i.e. a **1-hour-ahead forecast**. `arrivals` / `net_flow` are supported by the same code.
- **Data**: real Citi Bike JC trip history, June 2026 (git-ignored per §7.1). Rows lacking the
  weekly (168 h) lag are dropped, leaving a comparable supervised matrix across all models.

## Splits (rolling-origin only — §11.3)

Random K-fold is forbidden. The panel is split strictly by time:

- The latest `FINAL_TEST_HOURS` (72 h = 3 days) form an **untouched out-of-sample test**.
- The earlier development span is cross-validated with `CV_SPLITS` (3) **expanding-window**
  folds; each fold trains only on rows strictly before its validation window.
- Median imputation and standardisation live inside the model pipeline, so they are fit per
  fold — no test-set statistic leaks into training.

All geometry is in `config/forecasting.py`.

## Model zoo & tuning (§11.1, §11.5)

`GridSearchCV` with the rolling-origin folds tunes each algorithm; the search minimises WAPE.

| algorithm | family | grid |
|---|---|---|
| ridge | linear (scaled) | `alpha ∈ {0.1, 1, 10, 100}` |
| knn | distance (scaled) | `n_neighbors ∈ {5,15,30}`, `weights ∈ {uniform,distance}` |
| random_forest | bagged trees | `n_estimators ∈ {200,400}`, `max_depth ∈ {None,12,20}`, `min_samples_leaf ∈ {1,5}` |
| extra_trees | bagged trees | `n_estimators ∈ {200,400}`, `max_depth ∈ {None,20}`, `min_samples_leaf ∈ {1,5}` |
| gradient_boosting | boosting | `n_estimators ∈ {200,400}`, `learning_rate ∈ {0.05,0.1}`, `max_depth ∈ {2,3}` |
| hist_gradient_boosting | boosting | `learning_rate ∈ {0.05,0.1}`, `max_iter ∈ {300,600}`, `max_depth ∈ {None,8}` |

Seed 42 everywhere; the best trial is reproducible from config.

The **best algorithm is chosen by cross-validated WAPE on the development span**, never by the
untouched test window; the test window is scored once for the chosen model.

## Metrics (§11.4)

- **WAPE** = Σ|y−ŷ| / Σ|y|. Zero-denominator: 0.0 if the error is also 0, else NaN.
- **MAE** = mean |y−ŷ|.
- **MASE** = MAE / (in-sample seasonal-naive MAE on the development set, period = 168 h).
- **event-window WAPE** — reported separately; NaN when no row falls in an event window.
- **peak direction accuracy** — fraction of rows where sign(ŷ_t − y_{t−1}) matches sign(y_t − y_{t−1}).
- **forecast delta stability** — mean/‌std of the B4−B1 prediction delta.
- **bias** — mean(ŷ − y); flags systematic over- (positive) or under-forecasting (negative),
  the latter being the stockout-risk direction.
- **OCS (Operational Cost Score)** — the **data/domain-customised metric** (below).

### OCS — a metric that reflects this data and this product

Demand-forecast errors here are **operationally asymmetric**: under-forecasting a zone-hour
risks a **stockout** (a rider finds no bike), while over-forecasting wastes rebalancing and
risks **dock overflow**. The demand is also intermittent low-count (≈20 % zeros, median 2) with
wildly different zone scales (mean 0–12), so percentage metrics (MAPE/sMAPE) are unusable and a
scale-free, zero-robust score is required. OCS combines both:

```
OCS = ( shortage_cost · Σ max(y − ŷ, 0)  +  overflow_cost · Σ max(ŷ − y, 0) ) / Σ y
```

- Under-forecast bikes are charged `shortage_cost` (default 2.0), over-forecast bikes
  `overflow_cost` (default 1.0) — the operational-cost knobs of §11.5 / §14, set in
  `config/forecasting.py`.
- Normalising by total demand makes it scale-free and zero-robust, exactly like WAPE.
- **Reduction property**: with equal costs, `OCS == WAPE`. OCS is a principled generalisation of
  WAPE that bends it toward the rebalancing objective, and it links directly to the Phase 08
  cost model. The run also reports the raw under/over-forecast unit totals for interpretation.

## Ablation ladder (§11.2)

| level | features |
|---|---|
| B0 | seasonal naive (yhat_t = y_{t−168}) |
| B1 | demand history (lags/rolling/momentum) + calendar |
| B2 | B1 + raw article counts |
| B3 | B1 + LLM event features |
| B4 | B3 + graph-propagated features |

**Event-window caveat (honest, not hidden):** on the June evaluation window the only curated
events postdate the data (fixture events are 2026-07-12). The availability rule (§5.2) forces
every event/graph feature to zero, so B2–B4 reproduce B1 exactly. The runner verifies this by
calling `build_graph_features` at the window's last cutoff and confirming zero snapshots. Event
lift is therefore **not demonstrable on this window**; it requires an evaluation span that
overlaps curated events. The event-aware machinery itself is validated by the as-of leakage
tests (`tests/unit/test_graph_features.py`).

## Reproduce

```bash
make evaluate CITIBIKE_ZIP=data/raw/citibike/JC-202606-citibike-tripdata.csv.zip
# -> reports/phase06_results.json, reports/phase06_interpretation.md,
#    docs/img/phase06_*.png
```

## Results

See the **Forecasting results** section of the top-level `README.md` for the interpreted
leaderboard, best hyperparameters, feature importances, and ablation table from the latest run.
The raw numbers live in `reports/phase06_results.json` (regenerate with `make evaluate`).

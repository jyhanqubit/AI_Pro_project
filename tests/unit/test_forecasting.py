"""Forecasting unit tests. CLAUDE.md sections 11.3, 11.4, 17.

Covers metric definitions (incl. WAPE/MASE zero-denominator behaviour), the seasonal-naive
baseline, and the rolling-origin split guarantee that no training fold sees a future row.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from ml.forecasting.baselines import seasonal_naive_predict
from ml.forecasting.metrics import (
    forecast_delta_stability,
    mae,
    mase,
    peak_direction_accuracy,
    seasonal_naive_scale,
    wape,
)
from ml.forecasting.splits import final_holdout, rolling_origin_folds, to_hour_index

# --- Metrics --------------------------------------------------------------


def test_wape_basic():
    assert wape([10, 10], [9, 11]) == 2 / 20
    assert mae([10, 10], [9, 11]) == 1.0


def test_wape_zero_denominator():
    # All-zero actual, perfect fit -> 0.0; all-zero actual with error -> NaN (undefined).
    assert wape([0, 0], [0, 0]) == 0.0
    assert math.isnan(wape([0, 0], [1, 0]))


def test_mase_against_seasonal_scale():
    y = [float(i % 5) for i in range(40)]
    scale = seasonal_naive_scale(y, period=7)
    assert scale > 0
    # A model equal to truth has MASE 0; scale of 0/NaN yields NaN.
    assert mase([1, 2, 3], [1, 2, 3], scale) == 0.0
    assert math.isnan(mase([1, 2], [1, 3], 0.0))


def test_seasonal_naive_scale_insufficient_history():
    assert math.isnan(seasonal_naive_scale([1, 2, 3], period=7))


def test_peak_direction_accuracy():
    # prev=[5,5,5]; truth goes up, down, flat; pred matches up, down, but predicts up on flat.
    acc = peak_direction_accuracy([6, 4, 5], [7, 3, 6], [5, 5, 5])
    assert acc == 2 / 3


def test_delta_stability_zero_when_identical():
    d = forecast_delta_stability([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert d["mean_abs_delta"] == 0.0 and d["std_delta"] == 0.0


# --- Seasonal naive baseline ----------------------------------------------


def test_seasonal_naive_uses_weekly_lag_with_fallback():
    df = pd.DataFrame(
        {
            "dep_lag_168": [5.0, np.nan, np.nan],
            "dep_lag_24": [np.nan, 3.0, np.nan],
            "dep_lag_1": [np.nan, np.nan, 2.0],
        }
    )
    pred = seasonal_naive_predict(df, "departures")
    assert list(pred) == [5.0, 3.0, 2.0]


# --- Rolling-origin splits (no leakage) -----------------------------------


def _hours(n: int) -> list[datetime]:
    base = datetime(2026, 6, 1, tzinfo=UTC)
    return [base + timedelta(hours=i) for i in range(n)]


def test_final_holdout_splits_by_time():
    idx = to_hour_index(_hours(100))
    dev, test = final_holdout(idx, final_test_hours=10)
    assert len(test) == 10 and len(dev) == 90
    assert idx[dev].max() < idx[test].min()  # dev strictly before test


def test_rolling_origin_train_precedes_validation():
    idx = to_hour_index(_hours(200))
    folds = rolling_origin_folds(idx, n_splits=3, cv_test_hours=20)
    assert len(folds) == 3
    for train_pos, val_pos in folds:
        # Every training hour is strictly before every validation hour in the fold.
        assert idx[train_pos].max() < idx[val_pos].min()


def test_rolling_origin_is_expanding():
    idx = to_hour_index(_hours(200))
    folds = rolling_origin_folds(idx, n_splits=3, cv_test_hours=20)
    train_sizes = [len(tr) for tr, _ in folds]
    assert train_sizes == sorted(train_sizes)  # train set grows each fold

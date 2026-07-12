"""Seasonal-naive baseline (ablation B0). CLAUDE.md sections 11.1, 11.2.

The seasonal naive predicts the demand one seasonal period (one week) earlier: yhat_t =
y_{t-168}. This is exactly the leakage-safe ``dep_lag_168`` feature already built for each row,
with graceful fallback to the daily lag, the hourly lag, then zero when history is missing.
It defines both ablation level B0 and the MASE denominator (section 11.4).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config.features import TARGET_PREFIX


def seasonal_naive_predict(df: pd.DataFrame, target: str = "departures") -> np.ndarray:
    """Weekly seasonal-naive prediction for each row, with daily/hourly/zero fallback."""
    prefix = TARGET_PREFIX[target]
    weekly = df[f"{prefix}_lag_168"]
    daily = df[f"{prefix}_lag_24"]
    hourly = df[f"{prefix}_lag_1"]
    pred = weekly.fillna(daily).fillna(hourly).fillna(0.0)
    return pred.to_numpy(dtype=float)

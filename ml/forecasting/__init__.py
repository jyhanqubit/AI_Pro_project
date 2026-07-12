"""Forecasting: baselines, model zoo, temporal splits, metrics, and the ablation experiment.

CLAUDE.md section 11. All evaluation is rolling-origin; metrics come only from executed fits.
"""

from __future__ import annotations

from ml.forecasting.baselines import seasonal_naive_predict
from ml.forecasting.dataset import Panel, build_panel, load_real_panel
from ml.forecasting.experiment import run_experiment, usable_frame
from ml.forecasting.metrics import (
    evaluate,
    forecast_delta_stability,
    mae,
    mase,
    peak_direction_accuracy,
    seasonal_naive_scale,
    wape,
)
from ml.forecasting.models import algorithm_names, make_pipeline
from ml.forecasting.splits import final_holdout, rolling_origin_folds, to_hour_index

__all__ = [
    "seasonal_naive_predict",
    "Panel",
    "build_panel",
    "load_real_panel",
    "run_experiment",
    "usable_frame",
    "evaluate",
    "forecast_delta_stability",
    "mae",
    "mase",
    "peak_direction_accuracy",
    "seasonal_naive_scale",
    "wape",
    "algorithm_names",
    "make_pipeline",
    "final_holdout",
    "rolling_origin_folds",
    "to_hour_index",
]

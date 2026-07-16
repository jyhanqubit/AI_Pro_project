"""Forecasting experiment: GridSearch x algorithm zoo, ablation, feature selection.

CLAUDE.md sections 11.1-11.5. All splits are rolling-origin (section 11.3); GridSearch
cross-validates on the development span and the latest window is an untouched out-of-sample
test. Metrics are computed only from executed fits (section 11.4) and reported honestly,
including the event ablation collapsing to B1 on a window that predates the curated events.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.model_selection import GridSearchCV

from config.features import TARGET_PREFIX
from config.forecasting import (
    ABLATION_LEVELS,
    CV_SPLITS,
    CV_TEST_HOURS,
    FINAL_TEST_HOURS,
    OVERFLOW_COST,
    PRIMARY_TARGET,
    REQUIRED_FEATURES,
    SELECT_TOP_K,
    SHORTAGE_COST,
)
from ml.forecasting.baselines import seasonal_naive_predict
from ml.forecasting.dataset import Panel
from ml.forecasting.feature_selection import permutation_importances, select_top_k, wape_scorer
from ml.forecasting.metrics import evaluate, forecast_delta_stability, mae
from ml.forecasting.models import algorithm_names, make_pipeline
from ml.forecasting.splits import (
    final_holdout,
    holdout_by_time,
    rolling_origin_folds,
    to_hour_index,
)


def usable_frame(panel: Panel) -> pd.DataFrame:
    """Rows with the required history present (drops the warm-up week), time-sorted."""
    df = panel.df
    mask: np.ndarray = np.ones(len(df), dtype=bool)
    for col in REQUIRED_FEATURES:
        mask &= df[col].notna().to_numpy()
    return df.loc[mask].sort_values(["hour_start", "zone_id"]).reset_index(drop=True)


def _matrix(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    return df[cols].to_numpy(dtype=float)


# Panel columns that carry an as-of event/graph contribution; a test row is "event-affected" when
# any is non-zero (real news joined & available at that hour). Empty on the zero-overlap default.
_EVENT_SIGNAL_COLS = (
    "article_count_24h",
    "article_count_6h",
    "event_severity_sum",
    "transit_disruption_flag",
    "graph_distance_decayed_impact",
    "graph_neighbor_zone_impact",
    "graph_transit_exposure",
)


def _split_positions(
    df: pd.DataFrame, test_start: datetime | None = None
) -> tuple[np.ndarray, np.ndarray, list]:
    hour_idx = to_hour_index(list(df["hour_start"]))
    if test_start is not None:
        dev_pos, test_pos = holdout_by_time(list(df["hour_start"]), test_start)
    else:
        dev_pos, test_pos = final_holdout(hour_idx, FINAL_TEST_HOURS)
    folds = rolling_origin_folds(hour_idx[dev_pos], CV_SPLITS, CV_TEST_HOURS)
    return dev_pos, test_pos, folds


def _event_mask(df: pd.DataFrame, test_pos: np.ndarray) -> np.ndarray:
    """Boolean mask over the test rows that carry a non-zero as-of event/graph signal.

    Marks the rows an available event actually touches, so event-window WAPE measures the LLM
    feature effect where it applies. All-False on the zero-overlap default (no fabricated windows).
    """
    cols = [c for c in _EVENT_SIGNAL_COLS if c in df.columns]
    if not cols:
        return np.zeros(len(test_pos), dtype=bool)
    signal = df[cols].abs().sum(axis=1).to_numpy() > 0
    return signal[test_pos]


def run_experiment(
    panel: Panel, target: str = PRIMARY_TARGET, *, test_start: datetime | None = None
) -> dict[str, Any]:
    """Run the full Phase 06 experiment and return a JSON-serialisable result dict.

    ``test_start`` (aware) holds out every hour >= it as an expanding-window test set (e.g. train
    Jan-May, test June); ``None`` keeps the default trailing ``FINAL_TEST_HOURS`` holdout.
    """
    df = usable_frame(panel)
    prefix = TARGET_PREFIX[target]
    y = df[target].to_numpy(dtype=float)
    y_prev = df[f"{prefix}_lag_1"].to_numpy(dtype=float)

    dev_pos, test_pos, folds = _split_positions(df, test_start)
    if len(test_pos) == 0 or not folds:
        raise ValueError("insufficient temporal span for rolling-origin evaluation")

    y_dev, y_test = y[dev_pos], y[test_pos]
    y_prev_test = y_prev[test_pos]
    # MASE denominator: in-sample seasonal-naive MAE on the development set (section 11.4).
    scale = mae(y_dev, seasonal_naive_predict(df.iloc[dev_pos], target))
    # Real event-window mask: the test rows an available event actually touches (empty on the
    # zero-overlap default; non-empty once real overlapping news is joined).
    event_mask_test: np.ndarray = _event_mask(df, test_pos)

    def ev(pred: np.ndarray) -> dict[str, float]:
        """Evaluate a prediction against the test target with the configured cost weights."""
        return evaluate(
            y_test,
            pred,
            scale=scale,
            y_prev=y_prev_test,
            event_mask=event_mask_test,
            shortage_cost=SHORTAGE_COST,
            overflow_cost=OVERFLOW_COST,
        )

    b1_cols = panel.b1_cols

    results: dict[str, Any] = {
        "target": target,
        "n_rows_usable": int(len(df)),
        "n_dev": int(len(dev_pos)),
        "n_test": int(len(test_pos)),
        "n_cv_folds": len(folds),
        "n_features_b1": len(b1_cols),
        "seasonal_scale_mae": scale,
        "test_window_hours": int(np.ptp(to_hour_index(list(df["hour_start"]))[test_pos])) + 1
        if test_start is not None
        else FINAL_TEST_HOURS,
        "test_start": test_start.isoformat() if test_start is not None else None,
        "test_event_rows": int(event_mask_test.sum()),
        "ocs_shortage_cost": SHORTAGE_COST,
        "ocs_overflow_cost": OVERFLOW_COST,
    }

    # --- B0 seasonal naive reference -------------------------------------------------------
    snaive_test = seasonal_naive_predict(df.iloc[test_pos], target)
    results["B0_seasonal_naive"] = ev(snaive_test)

    # --- Stage 1: GridSearch over the algorithm zoo on B1 features --------------------------
    x_b1 = _matrix(df, b1_cols)
    x_dev, x_test = x_b1[dev_pos], x_b1[test_pos]

    algo_results: dict[str, Any] = {}
    fitted: dict[str, Any] = {}
    for kind in algorithm_names():
        pipe, grid = make_pipeline(kind)
        search = GridSearchCV(
            pipe, grid, scoring=wape_scorer, cv=folds, refit=True, n_jobs=1, error_score="raise"
        )
        search.fit(x_dev, y_dev)
        best = search.best_estimator_
        pred_test = best.predict(x_test)
        metrics = ev(pred_test)
        algo_results[kind] = {
            "best_params": {k: _clean(v) for k, v in search.best_params_.items()},
            "cv_wape": float(-search.best_score_),  # scorer is negated WAPE
            "test": metrics,
        }
        fitted[kind] = best

    results["algorithms"] = algo_results
    # Select the best algorithm by cross-validated WAPE (not by the untouched test window).
    best_algo = min(algo_results, key=lambda k: algo_results[k]["cv_wape"])
    results["best_algorithm"] = best_algo
    results["best_params"] = algo_results[best_algo]["best_params"]

    # --- Stage 2: feature-set ablation B0-B4 with the best algorithm ------------------------
    ablation: dict[str, Any] = {"B0": results["B0_seasonal_naive"]}
    for level in [lv for lv in ABLATION_LEVELS if lv != "B0"]:
        cols = panel.ablation_cols(level)
        xa = _matrix(df, cols)
        pipe, _ = make_pipeline(best_algo)
        est = clone(pipe).set_params(**results["best_params"])
        est.fit(xa[dev_pos], y_dev)
        pred = est.predict(xa[test_pos])
        ablation[level] = ev(pred)
        ablation[level]["n_features"] = len(cols)
    results["ablation"] = ablation

    # Event-aware delta stability: B4 minus B1 predictions on the test window (section 11.4).
    est_b1 = clone(make_pipeline(best_algo)[0]).set_params(**results["best_params"])
    est_b1.fit(x_dev, y_dev)
    pred_b1_test = est_b1.predict(x_test)
    cols_b4 = panel.ablation_cols("B4")
    xb4 = _matrix(df, cols_b4)
    est_b4 = clone(make_pipeline(best_algo)[0]).set_params(**results["best_params"])
    est_b4.fit(xb4[dev_pos], y_dev)
    pred_b4_test = est_b4.predict(xb4[test_pos])
    results["delta_stability_b4_vs_b1"] = forecast_delta_stability(pred_b1_test, pred_b4_test)

    # --- Stage 3: feature selection (permutation importance on the test holdout) ------------
    imps = permutation_importances(est_b1, x_test, y_test, b1_cols, n_repeats=10)
    top_k = select_top_k(imps, SELECT_TOP_K)
    results["permutation_importance"] = [
        {"feature": im.feature, "mean": im.mean, "std": im.std} for im in imps
    ]
    results["selected_top_k"] = top_k

    # Reduced re-fit on the top-k features only.
    x_sel = _matrix(df, top_k)
    est_sel = clone(make_pipeline(best_algo)[0]).set_params(**results["best_params"])
    est_sel.fit(x_sel[dev_pos], y_dev)
    pred_sel = est_sel.predict(x_sel[test_pos])
    results["reduced_model"] = {
        "k": len(top_k),
        "test": ev(pred_sel),
    }
    return results


def _clean(v: Any) -> Any:
    """JSON-friendly scalar (None/str for max_depth=None etc.)."""
    if v is None:
        return None
    if isinstance(v, (int, float, str, bool)):
        return v
    return str(v)

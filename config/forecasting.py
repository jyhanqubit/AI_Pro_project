"""Forecasting / evaluation configuration. CLAUDE.md sections 11 and 16.

Search spaces, split geometry, and the algorithm zoo live in configuration so the best
trial is reproducible from a saved config (section 11.5). All splits are strictly temporal
(rolling-origin); random K-fold is forbidden for forecasting evaluation (section 11.3).
"""

from __future__ import annotations

from typing import Any

# Reproducibility (section 16).
RANDOM_SEED = 42

# Primary forecasting target (section 4). The model predicts the current hour's demand from
# information available at the start of that hour (lags <= t-1, calendar of t) -> a 1-hour-ahead
# forecast at the H3 zone x local-hour grain.
PRIMARY_TARGET = "departures"
FORECAST_HORIZON_H = 1

# Rows need the full weekly lag to be comparable across models and to define the seasonal
# scale; warm-up rows lacking it are dropped from the supervised matrix.
SEASONAL_PERIOD_H = 168  # one week (the MASE / seasonal-naive period)
REQUIRED_FEATURES = ("dep_lag_1", "dep_lag_24", "dep_lag_168", "dep_roll_mean_24")

# Rolling-origin evaluation geometry (section 11.3). The latest FINAL_TEST_HOURS form an
# untouched out-of-sample test; GridSearch cross-validates on the earlier development span
# with CV_SPLITS expanding-window folds.
FINAL_TEST_HOURS = 72  # last 3 days held out
CV_SPLITS = 3
CV_TEST_HOURS = 48  # each expanding-window fold validates on 2 days

# Feature-selection target size (top-k by permutation importance) for the reduced re-fit.
SELECT_TOP_K = 12

# --- Domain-customised metric: Operational Cost Score (OCS) ---------------------------------
# Demand-forecast errors are operationally asymmetric on a bike system: under-forecasting a
# zone-hour risks a stockout (a rider finds no bike), while over-forecasting wastes rebalancing
# and risks dock overflow. OCS weights the two sides and normalises by total demand, so it is
# scale-free and zero-robust like WAPE. With SHORTAGE_COST == OVERFLOW_COST it reduces exactly
# to WAPE. These weights are the operational-cost knobs of section 11.5 / section 14.
SHORTAGE_COST = 2.0  # cost per bike of under-forecasting (stockout risk) — the costlier side
OVERFLOW_COST = 1.0  # cost per bike of over-forecasting (overflow / wasted relocation)

# --- Model zoo + GridSearch spaces (section 11.5) -------------------------------------------
# Each entry: estimator kind + a grid keyed by pipeline step. Linear / distance models are
# scaled; tree ensembles are not. Grids are deliberately modest to keep the run reproducible
# and bounded in wall-clock.

ALGORITHMS: dict[str, dict[str, Any]] = {
    "ridge": {
        "scale": True,
        "grid": {"model__alpha": [0.1, 1.0, 10.0, 100.0]},
    },
    "knn": {
        "scale": True,
        "grid": {
            "model__n_neighbors": [5, 15, 30],
            "model__weights": ["uniform", "distance"],
        },
    },
    "random_forest": {
        "scale": False,
        "grid": {
            "model__n_estimators": [200, 400],
            "model__max_depth": [None, 12, 20],
            "model__min_samples_leaf": [1, 5],
        },
    },
    "extra_trees": {
        "scale": False,
        "grid": {
            "model__n_estimators": [200, 400],
            "model__max_depth": [None, 20],
            "model__min_samples_leaf": [1, 5],
        },
    },
    "gradient_boosting": {
        "scale": False,
        "grid": {
            "model__n_estimators": [200, 400],
            "model__learning_rate": [0.05, 0.1],
            "model__max_depth": [2, 3],
        },
    },
    "hist_gradient_boosting": {
        "scale": False,
        "grid": {
            "model__learning_rate": [0.05, 0.1],
            "model__max_iter": [300, 600],
            "model__max_depth": [None, 8],
        },
    },
}

# Ablation feature groups (section 11.2). On an evaluation window that predates the only
# curated events, the event/graph groups are present but identically zero (documented, not
# hidden): B2..B4 collapse onto B1. See docs/EVALUATION_PROTOCOL.md.
ABLATION_LEVELS = ("B0", "B1", "B2", "B3", "B4")

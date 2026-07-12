"""Model zoo + GridSearch pipelines. CLAUDE.md sections 11.1, 11.5, 16.

Each algorithm is wrapped in a leakage-safe pipeline: median imputation (fit per CV fold, so
no test statistic leaks into training), optional standardisation for linear / distance models,
then the estimator. Grids come from ``config/forecasting.py`` so the best trial is reproducible
from config. Tree ensembles are seeded for determinism (section 16).
"""

from __future__ import annotations

from typing import Any

from sklearn.ensemble import (
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from config.forecasting import ALGORITHMS, RANDOM_SEED


def _estimator(kind: str) -> Any:
    if kind == "ridge":
        return Ridge(random_state=RANDOM_SEED)
    if kind == "knn":
        return KNeighborsRegressor()
    if kind == "random_forest":
        return RandomForestRegressor(random_state=RANDOM_SEED, n_jobs=-1)
    if kind == "extra_trees":
        return ExtraTreesRegressor(random_state=RANDOM_SEED, n_jobs=-1)
    if kind == "gradient_boosting":
        return GradientBoostingRegressor(random_state=RANDOM_SEED)
    if kind == "hist_gradient_boosting":
        return HistGradientBoostingRegressor(random_state=RANDOM_SEED)
    raise ValueError(f"unknown algorithm: {kind}")


def make_pipeline(kind: str) -> tuple[Pipeline, dict[str, list[Any]]]:
    """Return (pipeline, GridSearch grid) for an algorithm in the zoo."""
    if kind not in ALGORITHMS:
        raise ValueError(f"unknown algorithm: {kind}")
    steps: list[tuple[str, Any]] = [("impute", SimpleImputer(strategy="median"))]
    if ALGORITHMS[kind]["scale"]:
        steps.append(("scale", StandardScaler()))
    steps.append(("model", _estimator(kind)))
    grid: dict[str, list[Any]] = ALGORITHMS[kind]["grid"]
    return Pipeline(steps), grid


def algorithm_names() -> list[str]:
    return list(ALGORITHMS.keys())

"""Feature selection via permutation importance. CLAUDE.md sections 11.5, 20.

Permutation importance is model-agnostic and computed on a temporal holdout, so it reflects
out-of-sample predictive value rather than in-sample impurity gain. The top-k features feed a
reduced re-fit, letting the run report whether a smaller model matches the full one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.inspection import permutation_importance
from sklearn.metrics import make_scorer

from config.forecasting import RANDOM_SEED
from ml.forecasting.metrics import wape


@dataclass
class Importance:
    feature: str
    mean: float
    std: float


# GridSearch and permutation both minimise WAPE (greater_is_better=False -> scorer negates).
wape_scorer = make_scorer(wape, greater_is_better=False)


def permutation_importances(
    estimator: Any,
    x_val: np.ndarray,
    y_val: np.ndarray,
    feature_names: list[str],
    *,
    n_repeats: int = 10,
) -> list[Importance]:
    """Permutation importance on a holdout, ranked by mean WAPE degradation (descending)."""
    result = permutation_importance(
        estimator,
        x_val,
        y_val,
        scoring=wape_scorer,
        n_repeats=n_repeats,
        random_state=RANDOM_SEED,
        n_jobs=-1,
    )
    # scorer is negated WAPE; a positive importances_mean means shuffling worsened WAPE.
    imps = [
        Importance(
            feature=feature_names[i],
            mean=float(result.importances_mean[i]),
            std=float(result.importances_std[i]),
        )
        for i in range(len(feature_names))
    ]
    imps.sort(key=lambda im: im.mean, reverse=True)
    return imps


def select_top_k(importances: list[Importance], k: int) -> list[str]:
    """Names of the top-k features by mean importance."""
    return [im.feature for im in importances[:k]]

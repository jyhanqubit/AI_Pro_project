"""Experiment 2 against the committed promoted model (no raw trips needed): the tree-gain
importance is a deterministic function of the pickle, and SHAP on the committed serving matrix
reproduces exactly across two runs. shap is optional (not in the locks) -> skip with a reason."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from experiments.shap_explain import explain, tree_gain_importance
from ml.forecasting.promoted import load_promoted_model

HOLDOUT = Path("reports/v2/holdout")


@pytest.fixture(scope="module")
def served():
    model = load_promoted_model(HOLDOUT)
    assert model.is_servable
    snap = json.loads((HOLDOUT / "serving_features.json").read_text(encoding="utf-8"))
    feats = list(model.features)
    assert snap["feature_names"] == feats
    x_raw = np.array(
        [
            [z["features"][f] if z["features"][f] is not None else np.nan for f in feats]
            for z in snap["zones"]
        ],
        dtype=float,
    )
    x = model.estimator.named_steps["impute"].transform(x_raw)
    return model, feats, x


def test_tree_gain_importance_is_deterministic_and_covers_used_features(served) -> None:
    model, feats, _ = served
    hgb = model.estimator.named_steps["model"]
    gain1, count1 = tree_gain_importance(hgb, len(feats))
    gain2, count2 = tree_gain_importance(hgb, len(feats))
    assert np.array_equal(gain1, gain2) and np.array_equal(count1, count2)
    assert gain1.sum() > 0 and count1.sum() > 0
    # the weekly and hourly departure lags must be among the split features of a demand model
    assert count1[feats.index("dep_lag_168")] > 0 and count1[feats.index("dep_lag_1")] > 0


def test_shap_values_reproduce_and_sum_to_prediction(served) -> None:
    pytest.importorskip("shap")
    model, feats, x = served
    hgb = model.estimator.named_steps["model"]
    v1, base1, used1 = explain(x, hgb, feats)
    v2, base2, _ = explain(x, hgb, feats)
    assert np.array_equal(v1, v2) and base1 == base2
    assert used1.startswith("shap.TreeExplainer")
    pred = hgb.predict(x)
    assert np.allclose(v1.sum(axis=1) + base1, pred, atol=1e-3)

"""V2-03 LLM incremental-value ablation helper tests.

Cover the honesty-critical logic without needing the full panel: verdict from a CI, block
bootstrap direction, LLM cost estimate (actual mock = $0), and the event-signal mask.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ml.forecasting.llm_value import (
    _bootstrap_wape_delta,
    _event_mask,
    _llm_cost,
    _verdict,
)


def test_verdict_from_ci_sign():
    assert _verdict({"ci_lo": -0.05, "ci_hi": -0.01}) == "measured_improvement"  # WAPE dropped
    assert _verdict({"ci_lo": 0.01, "ci_hi": 0.05}) == "measured_regression"
    assert _verdict({"ci_lo": -0.02, "ci_hi": 0.02}) == "no_measurable_lift"


def test_bootstrap_detects_uniform_improvement():
    rng = np.random.default_rng(0)
    n = 600
    y = rng.integers(1, 10, size=n).astype(float)
    days = np.array([f"d{i % 20}" for i in range(n)])
    worse = y + rng.normal(0, 3, n)
    better = y + rng.normal(0, 0.2, n)  # much closer to truth
    out = _bootstrap_wape_delta(y, worse, better, days, n=300)
    assert out["delta_wape"] < 0  # better arm lowers WAPE
    assert out["ci_hi"] < 0  # CI entirely below zero -> improvement


def test_bootstrap_identical_predictions_zero_delta():
    y = np.array([1.0, 2.0, 3.0, 4.0] * 10)
    p = y + 0.5
    days = np.array([f"d{i % 5}" for i in range(len(y))])
    out = _bootstrap_wape_delta(y, p, p, days, n=100)
    assert out["delta_wape"] == 0.0
    assert out["ci_lo"] == 0.0 and out["ci_hi"] == 0.0


def test_llm_cost_actual_is_zero_estimate_positive(tmp_path):
    f = tmp_path / "news.jsonl"
    rows = [{"article_id": "a", "title": "t" * 100, "text": "x" * 400},
            {"article_id": "b", "title": "u" * 100, "text": "y" * 400}]
    f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    cost = _llm_cost(f)
    assert cost["actual_usd"] == 0.0  # mock provider is free
    assert cost["n_articles"] == 2
    assert cost["estimated_input_tokens"] > 0
    assert cost["estimated_real_usd"] >= 0.0


def test_llm_cost_missing_file_is_zero():
    cost = _llm_cost(None)
    assert cost["n_articles"] == 0
    assert cost["estimated_real_usd"] == 0.0


def test_event_mask_flags_nonzero_signal_rows():
    df = pd.DataFrame(
        {
            "article_count_24h": [0.0, 2.0, 0.0],
            "graph_distance_decayed_impact": [0.0, 0.0, 0.5],
            "departures": [1.0, 2.0, 3.0],  # non-signal col ignored
        }
    )
    mask = _event_mask(df)
    assert mask.tolist() == [False, True, True]

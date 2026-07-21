"""Unit tests for the LLM Feature Value (LFV) metric — the decision logic on synthetic data,
independent of the heavy trip pipeline."""

from __future__ import annotations

import numpy as np

from ml.forecasting.llm_feature_value import (
    INSUFFICIENT_SUPPORT,
    MEANINGFUL_NEGATIVE,
    MEANINGFUL_POSITIVE,
    NO_MEANINGFUL_EFFECT,
    llm_feature_value,
)


def _blocks(n: int, per: int = 10) -> list[int]:
    return [i // per for i in range(n)]


def test_meaningful_positive_when_llm_consistently_reduces_error():
    # Active rows: base is off by 5, LLM nails it -> large, consistent error reduction.
    n = 300
    rng = np.random.RandomState(0)
    y = rng.uniform(20, 40, n)
    active = np.zeros(n, dtype=bool)
    active[:200] = True
    pred_base = y.copy()
    pred_llm = y.copy()
    pred_base[active] = y[active] + 5.0  # base wrong on active rows
    pred_llm[active] = y[active] + 0.2   # LLM almost perfect on active rows
    r = llm_feature_value(y, pred_base, pred_llm, active, _blocks(n))
    assert r["decision"] == MEANINGFUL_POSITIVE
    assert r["llm_active_skill_score"] > 0
    assert r["significant"] is True
    assert r["active_error_gain_ci95"][0] > 0  # CI excludes 0 on the positive side
    assert r["claim_status"] == "measured"


def test_meaningful_negative_when_llm_consistently_worsens_error():
    n = 300
    rng = np.random.RandomState(1)
    y = rng.uniform(20, 40, n)
    active = np.zeros(n, dtype=bool)
    active[:200] = True
    pred_base = y.copy()
    pred_llm = y.copy()
    pred_base[active] = y[active] + 0.2  # base good
    pred_llm[active] = y[active] + 5.0   # LLM worse on active rows
    r = llm_feature_value(y, pred_base, pred_llm, active, _blocks(n))
    assert r["decision"] == MEANINGFUL_NEGATIVE
    assert r["llm_active_skill_score"] < 0
    assert r["active_error_gain_ci95"][1] < 0  # CI excludes 0 on the negative side


def test_no_meaningful_effect_when_predictions_identical():
    n = 300
    rng = np.random.RandomState(2)
    y = rng.uniform(20, 40, n)
    active = np.zeros(n, dtype=bool)
    active[:200] = True
    pred = y + rng.normal(0, 1, n)
    r = llm_feature_value(y, pred, pred.copy(), active, _blocks(n))  # base == llm
    assert r["decision"] == NO_MEANINGFUL_EFFECT
    assert r["significant"] is False


def test_no_meaningful_effect_when_no_systematic_difference():
    # Both arms are equal-quality (independent noise, same scale) -> per-row gain averages ~0 and the
    # CI covers 0 -> not meaningful. (Note: adding noise ON TOP of base would be a real negative
    # effect; here neither arm is systematically better.)
    n = 400
    rng = np.random.RandomState(3)
    y = rng.uniform(20, 40, n)
    active = np.ones(n, dtype=bool)
    pred_base = y + rng.normal(0, 5, n)
    pred_llm = y + rng.normal(0, 5, n)  # same quality, different draw -> no systematic gain
    r = llm_feature_value(y, pred_base, pred_llm, active, _blocks(n))
    assert r["decision"] == NO_MEANINGFUL_EFFECT
    assert r["significant"] is False


def test_insufficient_support_when_few_active_rows():
    n = 300
    rng = np.random.RandomState(4)
    y = rng.uniform(20, 40, n)
    active = np.zeros(n, dtype=bool)
    active[:20] = True  # below min_active=100
    pred_base = y.copy()
    pred_llm = y.copy()
    pred_base[active] = y[active] + 5.0
    pred_llm[active] = y[active]
    r = llm_feature_value(y, pred_base, pred_llm, active, _blocks(n))
    assert r["decision"] == INSUFFICIENT_SUPPORT
    assert r["claim_status"] == "blocked_data"
    assert r["llm_active_skill_score"] is None  # no verdict number faked


def test_active_subset_not_diluted_by_inactive_rows():
    # A real effect on a few hundred active rows should be visible on the active skill even when
    # thousands of inactive rows would wash out a global metric.
    n = 5000
    rng = np.random.RandomState(5)
    y = rng.uniform(20, 40, n)
    active = np.zeros(n, dtype=bool)
    active[:200] = True
    # Inactive rows carry real (identical for both arms) error, so they dilute a GLOBAL skill but
    # cancel out of the active-subset skill. This is exactly why the metric measures on the subset.
    noise = rng.normal(0, 4, n)
    pred_base = y + noise
    pred_llm = y + noise
    pred_base[active] = y[active] + 6.0
    pred_llm[active] = y[active] + 0.5
    r = llm_feature_value(y, pred_base, pred_llm, active, _blocks(n))
    assert r["decision"] == MEANINGFUL_POSITIVE
    # active skill is large; global skill is diluted toward 0 by the 4800 error-carrying inactive rows.
    assert r["llm_active_skill_score"] > abs(r["global_skill_score"])

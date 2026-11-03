"""Experiments 2 and 3 kernels (experiments/retrain_gate PSI + verdict, experiments/shap_explain
leakage mapping): pure, offline, reproducible — same input, same output."""

from __future__ import annotations

import numpy as np
import pytest

from experiments import retrain_gate as rg
from experiments.shap_explain import leakage_verdict


def test_psi_is_zero_for_identical_and_grows_with_shift() -> None:
    rng = np.random.default_rng(0)
    base = rng.normal(0, 1, 20_000)
    assert rg.psi(base, base) == pytest.approx(0.0, abs=1e-9)
    small = rg.psi(base, base + 0.1)
    large = rg.psi(base, base + 1.0)
    assert 0 < small < large
    assert rg.psi(base, base) == rg.psi(base.copy(), base.copy())  # reproducible


def test_psi_bins_use_baseline_deciles_and_nan_is_its_own_bin() -> None:
    base: np.ndarray = np.arange(1000, dtype=float)
    edges = rg.psi_bins(base)
    assert len(edges) == 9 and edges[0] == pytest.approx(99.9) and edges[-1] == pytest.approx(899.1)
    with_nan = np.concatenate([base, np.full(250, np.nan)])
    assert rg.psi(base, with_nan) > rg.psi(base, base)
    # few distinct values -> value bins, so a binary flag still gets a PSI
    flag_base = np.array([0.0] * 900 + [1.0] * 100)
    flag_cur = np.array([0.0] * 500 + [1.0] * 500)
    assert rg.psi(flag_base, flag_cur) > rg.PSI_REVIEW


def test_verdict_thresholds() -> None:
    assert rg.verdict(0.05, drop=False) == "keep"
    assert rg.verdict(0.05, drop=True) == "retrain"
    assert rg.verdict(0.10, drop=False) == "retrain"
    assert rg.verdict(0.24, drop=False) == "retrain"
    assert rg.verdict(0.25, drop=False) == "review_new_model"
    assert rg.verdict(0.90, drop=True) == "review_new_model"


@pytest.mark.parametrize(
    ("feature", "expected"),
    [
        ("dep_lag_1", "cutoff-safe"),
        ("arr_roll_mean_24", "window ends at t-1"),
        ("net_cumsum_day", "index < t"),
        ("cal_hour_cos", "known in advance"),
        ("member_share_lag_168", "cutoff-safe"),
        ("dep_expanding_mean", "excludes t"),
        ("mystery_feature", "inspect manually"),
    ],
)
def test_leakage_verdict_maps_every_served_feature_family(feature: str, expected: str) -> None:
    assert expected in leakage_verdict(feature)

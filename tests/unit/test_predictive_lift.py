"""Predictive-lift protocol (V2-02). CLAUDE.md §11, §17.

Validates the machinery on synthetic data with known outcomes: chronological split purge/embargo,
event-block bootstrap CI, and the honest verdict rule (measured only when coverage passes AND the CI
is strictly above 0; otherwise no_lift / negative_lift / inconclusive / blocked_data).
"""

from __future__ import annotations

from ml.forecasting.predictive_lift import (
    block_bootstrap_ci,
    chronological_split,
    lift_verdict,
    run_predictive_lift,
)


def test_split_is_time_ordered_and_embargoed() -> None:
    s = chronological_split(100, val_frac=0.2, test_frac=0.2, embargo=2)
    # No overlap, chronological, and an embargo gap between segments.
    assert s.train and s.val and s.test
    assert max(s.train) < min(s.val)
    assert max(s.val) < min(s.test)
    assert min(s.val) - max(s.train) > 1  # embargo purged at least one index
    assert min(s.test) - max(s.val) >= 1
    assert set(s.train) & set(s.val) == set()
    assert set(s.val) & set(s.test) == set()


def test_clear_positive_lift_is_measured() -> None:
    # M1 error consistently below M0 across many blocks → CI strictly above 0.
    m0 = [1.0] * 40
    m1 = [0.6] * 40
    blocks = [i // 4 for i in range(40)]  # 10 event blocks
    r = run_predictive_lift(m0, m1, blocks, coverage_ok=True, n_boot=500)
    assert r["verdict"] == "measured_improvement"
    assert r["claim_enabled"] is True
    assert r["ci_95"][0] > 0


def test_negative_lift_detected() -> None:
    m0 = [0.5] * 40
    m1 = [0.9] * 40  # M1 worse
    blocks = [i // 4 for i in range(40)]
    r = run_predictive_lift(m0, m1, blocks, coverage_ok=True, n_boot=500)
    assert r["verdict"] == "negative_lift"
    assert r["claim_enabled"] is False


def test_zero_gain_is_no_lift() -> None:
    m0 = [0.7] * 20
    m1 = [0.7] * 20  # identical → gain 0, degenerate CI [0, 0]
    blocks = [i // 4 for i in range(20)]
    r = run_predictive_lift(m0, m1, blocks, coverage_ok=True)
    assert r["verdict"] == "no_lift"
    assert r["ci_95"] == [0.0, 0.0]


def test_noisy_small_gain_is_inconclusive() -> None:
    # A tiny mean gain swamped by variance → CI straddles 0.
    m0 = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    m1 = [0.2, 1.8, 0.3, 1.7, 0.4, 1.6]  # mean gain ~0 with big spread
    blocks = [0, 1, 2, 3, 4, 5]
    r = run_predictive_lift(m0, m1, blocks, coverage_ok=True, n_boot=500)
    assert r["verdict"] in ("inconclusive", "no_lift")
    assert r["claim_enabled"] is False


def test_coverage_failure_blocks_claim_even_with_positive_ci() -> None:
    # Coverage gate not met → blocked_data regardless of the numbers.
    v = lift_verdict(0.4, 0.1, 0.7, coverage_ok=False)
    assert v["verdict"] == "blocked_data"
    assert v["claim_enabled"] is False


def test_bootstrap_is_deterministic() -> None:
    gains = [0.3, -0.1, 0.2, 0.4, -0.05, 0.25]
    blocks = [0, 0, 1, 1, 2, 2]
    a = block_bootstrap_ci(gains, blocks, seed=7, n_boot=300)
    b = block_bootstrap_ci(gains, blocks, seed=7, n_boot=300)
    assert a == b


def test_demo_run_is_honestly_blocked() -> None:
    from ml.forecasting.predictive_lift_demo import run

    r = run()
    # The curated demo fixture cannot pass the coverage gate → claim disabled, honestly.
    assert r["coverage_ok"] is False
    assert r["verdict"] == "blocked_data"
    assert r["claim_enabled"] is False
    assert r["coverage"]["unique_events"] >= 1  # real numbers, not fabricated

"""Predictive-lift protocol (V2-02). CLAUDE.md §11, §22.

Formalises "do event/graph features reduce holdout error?" with the honest claim rule from the V2
spec. The machinery here is pure and deterministic:

* ``chronological_split`` — train / validation / test split in time order with an **embargo**
  (purge) gap between segments so no window straddles the boundary.
* ``block_bootstrap_ci`` — a paired improvement CI resampled over **event blocks** (not individual
  rows), so autocorrelation within an event does not shrink the interval.
* ``lift_verdict`` — the claim rule: a *measured improvement* is asserted only when the coverage
  gate passes **and** the CI lies strictly above 0; otherwise the verdict is
  ``no_lift`` / ``negative_lift`` / ``inconclusive`` / ``blocked_data`` and the claim is disabled.

"Model-attributed", never "causal". Metrics only ever come from executed comparisons; a gain is
never fabricated to make the gate pass.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Split:
    train: list[int]
    val: list[int]
    test: list[int]
    embargo: int


def chronological_split(
    n: int, *, val_frac: float = 0.2, test_frac: float = 0.2, embargo: int = 1
) -> Split:
    """Time-ordered train/val/test indices with an embargo gap purged between segments."""
    if n <= 0:
        return Split([], [], [], embargo)
    n_test = max(1, int(round(n * test_frac)))
    n_val = max(1, int(round(n * val_frac)))
    test_start = n - n_test
    val_start = test_start - embargo - n_val
    train_end = val_start - embargo
    train = list(range(0, max(0, train_end)))
    val = list(range(max(0, val_start), max(0, val_start + n_val)))
    test = list(range(test_start, n))
    return Split(train, val, test, embargo)


def block_bootstrap_ci(
    gains: list[float],
    blocks: list[int],
    *,
    n_boot: int = 2000,
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """(mean_gain, ci_low, ci_high) resampling whole event blocks with replacement.

    ``gains[i] = loss(M0) - loss(M1)`` for row ``i`` (positive = M1 better). Rows are grouped by
    ``blocks[i]``; each bootstrap sample draws blocks (not rows) so within-event correlation is
    respected. Deterministic given ``seed``.
    """
    g = np.asarray(gains, dtype=np.float64)
    if g.size == 0:
        return 0.0, 0.0, 0.0
    b = np.asarray(blocks)
    uniq = list(dict.fromkeys(b.tolist()))
    by_block = {u: g[b == u] for u in uniq}
    if len(uniq) == 1 and float(np.std(g)) == 0.0:
        m = round(float(np.mean(g)), 6)
        return m, m, m  # degenerate (all-equal) → point interval, not a fake spread

    rng = np.random.RandomState(seed)
    means = np.empty(n_boot, dtype=np.float64)
    idx = np.arange(len(uniq))
    for i in range(n_boot):
        pick = rng.choice(idx, size=len(uniq), replace=True)
        sample = np.concatenate([by_block[uniq[j]] for j in pick])
        means[i] = sample.mean()
    lo = float(np.percentile(means, 100 * (alpha / 2)))
    hi = float(np.percentile(means, 100 * (1 - alpha / 2)))
    return round(float(g.mean()), 6), round(lo, 6), round(hi, 6)


def lift_verdict(mean_gain: float, ci_low: float, ci_high: float, *, coverage_ok: bool) -> dict:
    """Apply the V2-02 claim rule to a paired-improvement CI + coverage-gate result."""
    if not coverage_ok:
        verdict, enabled = "blocked_data", False
    elif ci_low > 0:
        verdict, enabled = "measured_improvement", True
    elif ci_high < 0:
        verdict, enabled = "negative_lift", False
    elif mean_gain == 0.0 and ci_low == 0.0 and ci_high == 0.0:
        verdict, enabled = "no_lift", False
    else:
        verdict, enabled = "inconclusive", False
    return {
        "verdict": verdict,
        "claim_enabled": enabled,
        "mean_gain": round(mean_gain, 6),
        "ci_95": [round(ci_low, 6), round(ci_high, 6)],
        "coverage_ok": coverage_ok,
    }


def run_predictive_lift(
    m0_errors: list[float],
    m1_errors: list[float],
    blocks: list[int],
    *,
    coverage_ok: bool,
    seed: int = 42,
    n_boot: int = 2000,
) -> dict:
    """Full paired M0-vs-M1 predictive-lift evaluation with the honest verdict."""
    if len(m0_errors) != len(m1_errors) or len(m0_errors) != len(blocks):
        raise ValueError("m0_errors, m1_errors, blocks must be the same length")
    gains = [a - b for a, b in zip(m0_errors, m1_errors, strict=True)]  # loss(M0) - loss(M1)
    mean_gain, lo, hi = block_bootstrap_ci(gains, blocks, seed=seed, n_boot=n_boot)
    verdict = lift_verdict(mean_gain, lo, hi, coverage_ok=coverage_ok)
    return {
        "n": len(gains),
        "n_blocks": len(set(blocks)),
        "mean_loss_m0": round(float(np.mean(m0_errors)), 6) if m0_errors else 0.0,
        "mean_loss_m1": round(float(np.mean(m1_errors)), 6) if m1_errors else 0.0,
        **verdict,
    }

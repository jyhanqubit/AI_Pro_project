"""V2-03 — **LLM Feature Value (LFV)**: one metric + decision for the question
"did adding the LLM-extracted event features *meaningfully* improve demand-forecast accuracy?"

The A2−A1 report already gives a global paired-bootstrap CI. This module turns that into a single,
decision-grade metric that is honest by construction:

1. **Skill score** = relative WAPE reduction from adding the LLM layer:
       skill = (WAPE_without_LLM − WAPE_with_LLM) / WAPE_without_LLM
   Positive ⇒ the LLM layer reduced error; negative ⇒ it hurt. Dimensionless, interpretable as a
   percentage error reduction.

2. **Measured where the feature can matter (LLM-active subset).** The LLM features are zero on almost
   every zone-hour, so a *global* skill is diluted toward 0 and hides the real effect. The headline is
   therefore the skill on the subset where the LLM feature is **active** (non-zero) — the CLAUDE.md
   "event-window WAPE" principle applied to the LLM-active window. The subset is defined by the
   feature being on, NOT by the outcome, so it cannot cherry-pick good rows.

3. **Significance + effect size, both required.** A block-bootstrap CI (same leakage-safe day-block
   resampling as the A2−A1 test) is computed on the paired per-row absolute-error gain over the active
   subset. The decision needs BOTH a non-trivial effect (|skill| ≥ `rel_threshold`) AND a CI that
   excludes 0 — so neither a tiny-but-significant nor a large-but-noisy effect is called "meaningful".

4. **Honest null.** Too few active rows ⇒ `INSUFFICIENT_SUPPORT` (blocked_data), no verdict faked. A
   CI that covers 0 ⇒ `NO_MEANINGFUL_EFFECT`. The metric reports the null as readily as a win.

Thresholds are pre-declared here (not tuned post-hoc): `rel_threshold=0.01` (a 1% relative WAPE
reduction) and `min_active=100` active zone-hours.

The core is a pure function `llm_feature_value(...)` so it is unit-testable on synthetic data
independent of the (heavy) trip pipeline.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ml.forecasting.predictive_lift import run_predictive_lift

REL_THRESHOLD = 0.01   # min |relative WAPE change| to count as a non-trivial effect
MIN_ACTIVE = 100       # min LLM-active zone-hours to render a verdict

# decision labels
MEANINGFUL_POSITIVE = "MEANINGFUL_POSITIVE"
MEANINGFUL_NEGATIVE = "MEANINGFUL_NEGATIVE"
NO_MEANINGFUL_EFFECT = "NO_MEANINGFUL_EFFECT"
INSUFFICIENT_SUPPORT = "INSUFFICIENT_SUPPORT"


def _wape(y: np.ndarray, p: np.ndarray) -> float | None:
    denom = float(np.abs(y).sum())
    if denom == 0.0:
        return None
    return float(np.abs(y - p).sum() / denom)


def _skill(wape_base: float | None, wape_llm: float | None) -> float | None:
    if wape_base is None or wape_llm is None or wape_base == 0.0:
        return None
    return (wape_base - wape_llm) / wape_base


def llm_feature_value(
    y_test,
    pred_base,
    pred_llm,
    active_mask,
    blocks,
    *,
    rel_threshold: float = REL_THRESHOLD,
    min_active: int = MIN_ACTIVE,
    seed: int = 0,
    n_boot: int = 2000,
) -> dict[str, Any]:
    """Compute the LLM Feature Value metric + decision.

    Args:
        y_test:      true target on the test rows.
        pred_base:   predictions WITHOUT the LLM feature layer (the A1 arm).
        pred_llm:    predictions WITH the LLM feature layer (the A2 arm).
        active_mask: bool per test row — True where any LLM feature is non-zero (the treatment set).
        blocks:      day-block id per test row (for the leakage-safe block bootstrap).
    """
    y = np.asarray(y_test, dtype=float)
    pb = np.asarray(pred_base, dtype=float)
    pl = np.asarray(pred_llm, dtype=float)
    m = np.asarray(active_mask, dtype=bool)
    blk = np.asarray(blocks)
    if not (len(y) == len(pb) == len(pl) == len(m) == len(blk)):
        raise ValueError("all inputs must be the same length")

    n_test = int(len(y))
    n_active = int(m.sum())

    global_skill = _skill(_wape(y, pb), _wape(y, pl))

    active_skill: float | None = None
    ci: list[float] | None = None
    mean_gain: float | None = None
    significant = False

    if n_active >= min_active:
        active_skill = _skill(_wape(y[m], pb[m]), _wape(y[m], pl[m]))
        err_base = np.abs(y[m] - pb[m]).tolist()
        err_llm = np.abs(y[m] - pl[m]).tolist()
        lift = run_predictive_lift(err_base, err_llm, blk[m].tolist(),
                                   coverage_ok=True, seed=seed, n_boot=n_boot)
        mean_gain = lift["mean_gain"]
        ci = lift["ci_95"]
        significant = ci[0] > 0 or ci[1] < 0

    # decision (needs both effect size and significance)
    if n_active < min_active:
        decision, claim_status = INSUFFICIENT_SUPPORT, "blocked_data"
    elif active_skill is None:
        decision, claim_status = INSUFFICIENT_SUPPORT, "blocked_data"
    elif active_skill >= rel_threshold and ci is not None and ci[0] > 0:
        decision, claim_status = MEANINGFUL_POSITIVE, "measured"
    elif active_skill <= -rel_threshold and ci is not None and ci[1] < 0:
        decision, claim_status = MEANINGFUL_NEGATIVE, "measured"
    else:
        decision, claim_status = NO_MEANINGFUL_EFFECT, "measured"

    pct = None if active_skill is None else round(active_skill * 100, 2)
    mag = None if pct is None else abs(pct)
    interp = {
        MEANINGFUL_POSITIVE: f"LLM features cut error {mag}% on active zone-hours (CI excludes 0).",
        MEANINGFUL_NEGATIVE: f"LLM features raised error {mag}% on active zone-hours (CI excludes 0).",
        NO_MEANINGFUL_EFFECT: "No meaningful accuracy change from the LLM features "
                              "(effect below threshold or CI covers 0).",
        INSUFFICIENT_SUPPORT: f"Only {n_active} LLM-active zone-hours (< {min_active}); "
                              "not enough support to decide.",
    }[decision]

    return {
        "metric": "llm_feature_value",
        "decision": decision,
        "claim_status": claim_status,
        "llm_active_skill_score": None if active_skill is None else round(active_skill, 4),
        "llm_active_skill_pct": pct,
        "global_skill_score": None if global_skill is None else round(global_skill, 4),
        "significant": bool(significant),
        "active_error_gain_mean": mean_gain,
        "active_error_gain_ci95": ci,
        "n_test_rows": n_test,
        "n_llm_active_rows": n_active,
        "thresholds": {"rel_threshold": rel_threshold, "min_active": min_active},
        "definition": "skill = (WAPE_without_LLM - WAPE_with_LLM)/WAPE_without_LLM on the LLM-active "
                      "subset; decision = MEANINGFUL iff |skill| >= rel_threshold AND bootstrap CI "
                      "on paired abs-error gain excludes 0; else NO_MEANINGFUL_EFFECT / "
                      "INSUFFICIENT_SUPPORT. Positive skill = error reduced.",
        "interpretation": interp,
    }

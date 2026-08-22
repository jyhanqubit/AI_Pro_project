"""Asymmetric-cost forecasting: does predicting an upper quantile lower operational cost?

The promoted model is fit with a **symmetric** loss (squared error), so it targets the conditional
mean. Operationally the two error directions are not symmetric: under-forecasting a zone-hour risks
a stockout (a rider finds no bike) while over-forecasting only wastes a relocation, and section
11.5 / 14 price that at ``SHORTAGE_COST`` vs ``OVERFLOW_COST``. Until now that asymmetry lived only
in the metric (OCS) and in the rebalancing objective — never in the fit.

The newsvendor result says where the fit *should* sit: with shortage cost ``c_s`` and overflow cost
``c_o`` the cost-minimising point forecast is the quantile

    q* = c_s / (c_s + c_o)

which is 2/3 for the OCS weights (2:1) and 0.75 for the rebalancing weights (3:1), not the median.
So this is a **pre-registered prediction**, not a search: WAPE should get slightly worse (it scores
a symmetric objective) while OCS should improve, with the minimum near q*.

The sweep refits the promoted algorithm per rolling-origin window (same geometry and leakage rules
as ``h3_multiholdout``) at each quantile and reports both metrics, so a reader can see the tradeoff
rather than a single flattering number. If OCS does not improve, that is reported as-is.

    python -m ml.forecasting.quantile_cost --data-dir data/raw/citibike --windows 3
    make v2-quantile-cost

Output: ``reports/v2/holdout/quantile_cost.json``.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from config.forecasting import (
    OVERFLOW_COST,
    PRIMARY_TARGET,
    RANDOM_SEED,
    SHORTAGE_COST,
)
from ml.forecasting.dataset import Panel, load_real_panel
from ml.forecasting.experiment import usable_frame
from ml.forecasting.h3_multiholdout import bounded_holdout, build_monthly_windows
from ml.forecasting.metrics import bias, mae, operational_cost_score, wape

OUT_PATH = Path("reports/v2/holdout/quantile_cost.json")

# The promoted model's algorithm and hyperparameters, held fixed so only the loss changes.
PROMOTED_PARAMS = {"learning_rate": 0.1, "max_iter": 300, "max_depth": 8}
DEFAULT_QUANTILES = (0.50, 0.60, 0.667, 0.75, 0.80)


def newsvendor_quantile(shortage_cost: float, overflow_cost: float) -> float:
    """q* = c_s / (c_s + c_o) — the cost-minimising quantile for an asymmetric linear cost."""
    total = shortage_cost + overflow_cost
    return shortage_cost / total if total > 0 else 0.5


def _pipeline(loss: str, quantile: float | None) -> Pipeline:
    kw: dict[str, Any] = dict(random_state=RANDOM_SEED, **PROMOTED_PARAMS)
    if loss == "quantile":
        kw["loss"] = "quantile"
        kw["quantile"] = quantile
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("model", HistGradientBoostingRegressor(**kw)),
        ]
    )


def score(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """WAPE (symmetric accuracy) alongside OCS (asymmetric operational cost) and the bias sign."""
    cost = operational_cost_score(
        y_true, y_pred, shortage_cost=SHORTAGE_COST, overflow_cost=OVERFLOW_COST
    )
    return {
        "wape": round(float(wape(y_true, y_pred)), 4),
        "mae": round(float(mae(y_true, y_pred)), 4),
        "ocs": round(float(cost["ocs"]), 4),
        "shortage_units": round(float(cost["shortage_units"]), 1),
        "overflow_units": round(float(cost["overflow_units"]), 1),
        "bias": round(float(bias(y_true, y_pred)), 4),
    }


def run_arm(
    df: pd.DataFrame,
    cols: list[str],
    target: str,
    windows: list[tuple[datetime, datetime]],
    *,
    loss: str,
    quantile: float | None,
) -> dict[str, Any]:
    """Refit one loss setting on every rolling-origin window and score it out-of-sample."""
    x_all = df[cols].to_numpy(dtype=float)
    y_all = df[target].to_numpy(dtype=float)
    hours = list(df["hour_start"])

    per_window: list[dict[str, Any]] = []
    for start, end in windows:
        train_pos, test_pos = bounded_holdout(hours, start, end)
        if train_pos.size == 0 or test_pos.size == 0:
            continue
        pipe = _pipeline(loss, quantile)
        pipe.fit(x_all[train_pos], y_all[train_pos])
        pred = np.asarray(pipe.predict(x_all[test_pos]), dtype=float)
        per_window.append(
            {
                "window": f"{start:%Y-%m}",
                "n_test": int(test_pos.size),
                **score(y_all[test_pos], pred),
            }
        )
    if not per_window:
        raise SystemExit("no usable window")

    def agg(key: str) -> dict[str, float]:
        vals = [w[key] for w in per_window]
        return {
            "mean": round(float(np.mean(vals)), 4),
            "std": round(float(np.std(vals, ddof=0)), 4),
        }

    return {
        "loss": loss,
        "quantile": quantile,
        "windows": per_window,
        "aggregate": {k: agg(k) for k in ("wape", "ocs", "mae", "bias")},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ml.forecasting.quantile_cost")
    ap.add_argument("--data-dir", default="data/raw/citibike")
    ap.add_argument("--target", default=PRIMARY_TARGET)
    ap.add_argument("--windows", type=int, default=3)
    ap.add_argument(
        "--quantiles",
        default=",".join(str(q) for q in DEFAULT_QUANTILES),
        help="comma-separated quantiles to sweep",
    )
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ns = ap.parse_args(argv)

    q_star = newsvendor_quantile(SHORTAGE_COST, OVERFLOW_COST)
    quantiles = [float(q) for q in ns.quantiles.split(",") if q.strip()]
    print(
        f"asymmetric-cost sweep — shortage:overflow = {SHORTAGE_COST}:{OVERFLOW_COST} "
        f"=> newsvendor q* = {q_star:.3f}"
    )

    panel: Panel = load_real_panel(Path(ns.data_dir))
    df = usable_frame(panel)
    if df.empty:
        raise SystemExit("no usable rows (need a real multi-month trip backfill)")
    cols = list(panel.b1_cols)  # the same dfv1 feature set the promoted model uses
    windows = build_monthly_windows(df["hour_start"], ns.windows)
    print(
        f"usable rows={len(df)}  zones={df['zone_id'].nunique()}  "
        f"features={len(cols)}  windows={[f'{a:%Y-%m}' for a, _ in windows]}"
    )

    arms = [run_arm(df, cols, ns.target, windows, loss="squared_error", quantile=None)]
    for q in quantiles:
        arms.append(run_arm(df, cols, ns.target, windows, loss="quantile", quantile=q))

    baseline = arms[0]
    print(f"\n{'loss':<22}{'WAPE':>9}{'OCS':>9}{'bias':>9}   vs baseline OCS")
    for a in arms:
        label = "squared_error (기준)" if a["quantile"] is None else f"quantile q={a['quantile']}"
        w, o, b = (
            a["aggregate"]["wape"]["mean"],
            a["aggregate"]["ocs"]["mean"],
            a["aggregate"]["bias"]["mean"],
        )
        delta = (
            (o - baseline["aggregate"]["ocs"]["mean"]) / baseline["aggregate"]["ocs"]["mean"] * 100
        )
        print(f"{label:<22}{w:>9.4f}{o:>9.4f}{b:>+9.3f}   {delta:>+7.2f}%")

    best = min(arms, key=lambda a: a["aggregate"]["ocs"]["mean"])
    ocs_gain = (
        (baseline["aggregate"]["ocs"]["mean"] - best["aggregate"]["ocs"]["mean"])
        / baseline["aggregate"]["ocs"]["mean"]
        * 100
    )
    wape_cost = (
        (best["aggregate"]["wape"]["mean"] - baseline["aggregate"]["wape"]["mean"])
        / baseline["aggregate"]["wape"]["mean"]
        * 100
    )
    improved = best["quantile"] is not None and ocs_gain > 0

    stamp = datetime.now(UTC)
    payload = {
        "run_id": f"run_v2-01q_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": str(ns.out),
        "mode": "historical_replay",
        "claim_status": "measured",
        "freshness": stamp.isoformat(),
        "grain": "H3 zone x local hour",
        "target": ns.target,
        "algorithm": "hist_gradient_boosting",
        "params": PROMOTED_PARAMS,
        "cost_weights": {"shortage": SHORTAGE_COST, "overflow": OVERFLOW_COST},
        "newsvendor_q_star": round(q_star, 4),
        "prediction_registered": (
            "Newsvendor theory puts the cost-minimising point forecast at q* = c_s/(c_s+c_o); WAPE "
            "should worsen slightly while OCS improves, with the OCS minimum near q*."
        ),
        "arms": arms,
        "best_by_ocs": {"loss": best["loss"], "quantile": best["quantile"]},
        "ocs_improvement_pct": round(ocs_gain, 2),
        "wape_cost_pct": round(wape_cost, 2),
        "verdict": "ocs_improved" if improved else "no_ocs_improvement",
        "note": (
            "Only the loss changes; algorithm, hyperparameters, features, windows and seed stay "
            "fixed. WAPE and OCS are reported together because trading one for the other is the "
            "whole point — a single metric would hide the tradeoff."
        ),
    }
    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nbest by OCS: {best['loss']} q={best['quantile']}")
    print(f"  OCS {ocs_gain:+.2f}%  (WAPE {wape_cost:+.2f}%)  -> {payload['verdict']}")
    print(f"report -> {ns.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

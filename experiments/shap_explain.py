"""Experiment 2 — SHAP explanations for the promoted HistGradientBoosting model.

Model: ``reports/v2/holdout/promoted_model.joblib`` (Pipeline: median imputer -> HGB), loaded through
the same version-checked loader the API uses. Rows: a seeded sample of the real Jersey City panel
(``experiments/_panel``) restricted to a month range (default the two months *after* the training
span, so the explanation is out-of-sample).

Outputs (``reports/agent_experiments/shap_explain.json``):
  * global: mean |SHAP| per feature, top 10;
  * local: top-5 contributions for three representative rows (highest, median, lowest prediction);
  * baseline importances: total split gain from the fitted trees (the estimator's own structure)
    and permutation importance (MAE, seeded) on the same sample; rank comparison with SHAP;
  * leakage audit: every top feature mapped to how ``pipelines/features/lags.py`` builds it.

Explainer: ``shap.TreeExplainer`` on the HGB estimator with the imputed matrix (what the model sees);
if the installed shap cannot handle the estimator, the script falls back to ``shap.Explainer`` and
records which path ran.

Usage: python -m experiments.shap_explain [--months 2026-08 2026-09] [--n 3000] [--seed 42]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from experiments._panel import DATA_DIR, load_usable_panel
from ml.forecasting.promoted import load_promoted_model

OUT_DEFAULT = Path("reports/agent_experiments/shap_explain.json")
HOLDOUT_DIR = Path("reports/v2/holdout")

# How each feature family is built (pipelines/features/lags.py, calendar.py). "cutoff-safe" means
# every value is a function of hours strictly before t, or of the calendar of t itself.
LEAKAGE_RULES: dict[str, str] = {
    "lag": "{p}_lag_k = series[t-k] (lags.py l.28-30: j = i - k, None if j < 0) — hours < t only: cutoff-safe",
    "roll_mean": "{p}_roll_mean_w = mean(series[t-w:t]) (lags.py l.34) — window ends at t-1, shifted: cutoff-safe",
    "momentum": "{p}_momentum = mean(series[t-3:t]) / mean(series[t-24:t]) (lags.py l.45-46) — prior hours only: cutoff-safe",
    "expanding_mean": "{p}_expanding_mean = mean(series[:t]) (lags.py l.50) — all prior hours, excludes t: cutoff-safe",
    "net_cumsum_day": "sum of net_flow over hours of the same local day with index < t (lags.py l.56-57): cutoff-safe",
    "member_share": "member_share_lag_k = member share at t-k (lags.py l.60-62): cutoff-safe",
    "cal": "calendar of hour t itself (hour, weekday, weekend, rush, holiday) — known in advance, not demand information: cutoff-safe",
}


def leakage_verdict(feature: str) -> str:
    p = feature.split("_")[0]
    if feature.startswith("cal_"):
        return LEAKAGE_RULES["cal"]
    if feature == "net_cumsum_day":
        return LEAKAGE_RULES["net_cumsum_day"]
    if feature.startswith("member_share_lag_"):
        return LEAKAGE_RULES["member_share"]
    for key in ("lag", "roll_mean", "momentum", "expanding_mean"):
        if f"_{key}" in feature:
            return LEAKAGE_RULES[key].format(p=p)
    return "unknown feature family — inspect manually"


def _month_mask(df: pd.DataFrame, months: list[str]) -> np.ndarray:
    local = pd.to_datetime(df["hour_start"], utc=True).dt.tz_convert("America/New_York")
    return local.dt.strftime("%Y-%m").isin(months).to_numpy()


def tree_gain_importance(hgb: Any, n_features: int) -> tuple[np.ndarray, np.ndarray]:
    """Total split gain per feature summed over every tree (sklearn HGB internals)."""
    gain = np.zeros(n_features)
    count = np.zeros(n_features)
    for tree_group in hgb._predictors:
        for tree in tree_group:
            nodes = tree.nodes
            split = nodes[~nodes["is_leaf"].astype(bool)]
            np.add.at(gain, split["feature_idx"], split["gain"])
            np.add.at(count, split["feature_idx"], 1)
    return gain, count


def explain(x: np.ndarray, hgb: Any, feature_names: list[str]) -> tuple[np.ndarray, float, str]:
    import shap  # type: ignore[import-untyped]

    try:
        ex = shap.TreeExplainer(hgb)
        vals = ex.shap_values(x)
        base = float(np.ravel(ex.expected_value)[0])
        return np.asarray(vals), base, "shap.TreeExplainer (sklearn HistGradientBoostingRegressor)"
    except Exception as exc:  # noqa: BLE001 — fall back and record why
        ex = shap.Explainer(hgb.predict, x, seed=0)
        out = ex(x)
        return (
            np.asarray(out.values),
            float(np.ravel(out.base_values)[0]),
            f"shap.Explainer fallback because TreeExplainer failed: {exc!r}",
        )


def _git_commit() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout.strip()
        return sha + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv: list[str] | None = None) -> dict[str, Any]:
    ap = argparse.ArgumentParser(prog="experiments.shap_explain", description=__doc__)
    ap.add_argument("--data-dir", type=Path, default=DATA_DIR)
    ap.add_argument(
        "--months",
        nargs="+",
        default=["2026-08", "2026-09"],
        help="local months to sample rows from",
    )
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ns = ap.parse_args(argv)

    t0 = time.perf_counter()
    model = load_promoted_model(HOLDOUT_DIR)
    assert model.is_servable, "promoted model not servable"
    pipe: Any = model.estimator
    hgb = pipe.named_steps["model"]
    feats = list(model.features)

    df, _b1, files = load_usable_panel(ns.data_dir)
    mask = _month_mask(df, ns.months)
    pool = df.loc[mask]
    rng = np.random.default_rng(ns.seed)
    idx = np.sort(rng.choice(len(pool), size=min(ns.n, len(pool)), replace=False))
    sample = pool.iloc[idx].reset_index(drop=True)
    x_raw = sample[feats].to_numpy(dtype=float)
    y = sample[model.target].to_numpy(dtype=float)
    x = pipe.named_steps["impute"].transform(x_raw)  # what the HGB sees
    pred = hgb.predict(x)

    shap_vals, base_value, explainer_used = explain(x, hgb, feats)
    mean_abs = np.abs(shap_vals).mean(axis=0)
    order = np.argsort(-mean_abs)
    glob = [
        {
            "rank": r + 1,
            "feature": feats[i],
            "mean_abs_shap": float(mean_abs[i]),
            "mean_shap": float(shap_vals[:, i].mean()),
        }
        for r, i in enumerate(order[:10])
    ]

    # local: highest / median / lowest predicted rows
    reps = {
        "highest_prediction": int(np.argmax(pred)),
        "median_prediction": int(np.argsort(pred)[len(pred) // 2]),
        "lowest_prediction": int(np.argmin(pred)),
    }
    local = []
    for label, r in reps.items():
        contrib = shap_vals[r]
        top = np.argsort(-np.abs(contrib))[:5]
        local.append(
            {
                "which": label,
                "zone_id": str(sample.loc[r, "zone_id"]),
                "hour_start": str(sample.loc[r, "hour_start"]),
                "actual_departures": float(y[r]),
                "predicted_departures": float(pred[r]),
                "base_value": base_value,
                "sum_shap": float(contrib.sum()),
                "top5": [
                    {"feature": feats[i], "value": float(x[r, i]), "shap": float(contrib[i])}
                    for i in top
                ],
            }
        )

    # baseline importances
    gain, count = tree_gain_importance(hgb, len(feats))
    from sklearn.inspection import permutation_importance

    pi = permutation_importance(
        pipe,
        x_raw,
        y,
        scoring="neg_mean_absolute_error",
        n_repeats=5,
        random_state=ns.seed,
        n_jobs=1,
    )

    def rank(v: Any) -> dict[str, int]:
        return {feats[i]: int(r + 1) for r, i in enumerate(np.argsort(-np.asarray(v)))}

    r_shap, r_gain, r_perm = rank(mean_abs), rank(gain), rank(pi.importances_mean)
    comparison: list[dict[str, Any]] = sorted(
        (
            {
                "feature": f,
                "shap_rank": r_shap[f],
                "gain_rank": r_gain[f],
                "perm_rank": r_perm[f],
                "mean_abs_shap": float(mean_abs[i]),
                "total_gain": float(gain[i]),
                "split_count": int(count[i]),
                "perm_importance_mae": float(pi.importances_mean[i]),
                "shap_vs_gain_rank_gap": abs(r_shap[f] - r_gain[f]),
            }
            for i, f in enumerate(feats)
        ),
        key=lambda d: d["shap_rank"],
    )
    big_gap = [
        c["feature"]
        for c in comparison
        if c["shap_vs_gain_rank_gap"] >= 5 and min(c["shap_rank"], c["gain_rank"]) <= 10
    ]

    leakage = [
        {"feature": g["feature"], "rank": g["rank"], "verdict": leakage_verdict(g["feature"])}
        for g in glob
    ]

    result = {
        "experiment": "shap_explain",
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(),
        "command": "python -m experiments.shap_explain --months "
        + " ".join(ns.months)
        + f" --n {ns.n} --seed {ns.seed}",
        "seed": ns.seed,
        "model": {
            "artifact": str(HOLDOUT_DIR / "promoted_model.joblib"),
            "run_id": model.manifest.get("run_id"),
            "algorithm": model.manifest.get("algorithm"),
            "params": model.manifest.get("params"),
            "n_trees_fitted": int(hgb.n_iter_),
            "trained_through_hour": model.manifest.get("trained_through_hour"),
            "feature_version": model.manifest.get("feature_version"),
            "n_features": len(feats),
        },
        "data": {
            "source_files": files,
            "months": ns.months,
            "rows_in_months": int(mask.sum()),
            "rows_sampled": int(len(sample)),
            "zones_sampled": int(sample.zone_id.nunique()),
            "out_of_sample": all(m > "2026-07" for m in ns.months),
        },
        "explainer": explainer_used,
        "base_value": base_value,
        "sample_wape": float(np.abs(y - pred).sum() / np.abs(y).sum()),
        "global_top10": glob,
        "local_examples": local,
        "importance_comparison": comparison,
        "large_rank_gap_features": big_gap,
        "leakage_audit": leakage,
        "elapsed_s": round(time.perf_counter() - t0, 1),
    }
    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    _print(result)
    print(f"\nwrote {ns.out}")
    return result


def _print(res: dict[str, Any]) -> None:
    print(
        f"explainer: {res['explainer']} | rows {res['data']['rows_sampled']} of {res['data']['rows_in_months']} ({res['data']['months']}) | sample WAPE {res['sample_wape']:.4f}"
    )
    print("\nglobal mean|SHAP| top 10:")
    for g in res["global_top10"]:
        print(f"  {g['rank']:2d}. {g['feature']:24s} {g['mean_abs_shap']:.4f}")
    print("\nSHAP vs gain vs permutation (top 12 by SHAP):")
    for c in res["importance_comparison"][:12]:
        print(
            f"  {c['feature']:24s} shap#{c['shap_rank']:2d} gain#{c['gain_rank']:2d} perm#{c['perm_rank']:2d}"
        )
    print("large rank gap (|shap-gain| >= 5 within top10):", res["large_rank_gap_features"])
    for ex in res["local_examples"]:
        print(
            f"\n{ex['which']}: zone {ex['zone_id']} {ex['hour_start']} actual {ex['actual_departures']:.0f} pred {ex['predicted_departures']:.2f}"
        )
        for t in ex["top5"]:
            print(f"    {t['feature']:24s} value {t['value']:9.3f}  shap {t['shap']:+.3f}")


if __name__ == "__main__":
    sys.exit(0 if main() else 1)

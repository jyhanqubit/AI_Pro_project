"""Experiment 3 — retrain decision from feature drift (PSI) and champion performance by month.

Baseline distribution: the feature values of the *baseline months* (default 2026-01..05, the
span the user named; the promoted model's own selection span was 2026-01..04 and its final fit
ran through 2026-07). For every later month the Population Stability Index of each B1 feature is
computed against the baseline, with continuous features binned at the baseline's deciles
(10 bins; NaN is its own bin) and low-cardinality features binned by value.

Performance: the champion's WAPE on each month (champion = the committed promoted model). Months
up to 2026-07 are inside the champion's final training span and are labelled in-sample; later
months are out-of-sample. The reference WAPE for the "performance held" rule is the committed
multi-holdout mean (reports/v2/holdout/h3_multiholdout.json, out-of-sample May..Jul), and a month
counts as a drop when its WAPE exceeds that reference by more than ``--drop-pct`` percent.

Rule (per month): max PSI over the key features < 0.10 and no drop -> keep; 0.10..0.25 or a drop
-> retrain; >= 0.25 -> review (new model). When any month says retrain, a challenger is fit on
baseline..(month-1) with the champion's algorithm and hyper-parameters and compared with the
champion on the same evaluation month.

Usage: python -m experiments.retrain_gate [--baseline-months 2026-01 ... 2026-05] [--seed 42]
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
from ml.forecasting.metrics import mae, wape
from ml.forecasting.models import make_pipeline
from ml.forecasting.promoted import load_promoted_model

OUT_DEFAULT = Path("reports/agent_experiments/retrain_gate.json")
HOLDOUT_DIR = Path("reports/v2/holdout")
PSI_KEEP, PSI_REVIEW = 0.10, 0.25


# --- PSI kernel (pure) -----------------------------------------------------------------------


def psi_bins(baseline: np.ndarray, n_bins: int = 10) -> np.ndarray:
    """Decile edges of the finite baseline values (duplicates collapsed); value-bins when few uniques."""
    b = baseline[np.isfinite(baseline)]
    if b.size == 0:
        return np.array([])
    uniques = np.unique(b)
    if uniques.size <= n_bins:
        mids = (uniques[:-1] + uniques[1:]) / 2.0
        return mids
    edges = np.quantile(b, np.linspace(0, 1, n_bins + 1)[1:-1])
    return np.unique(edges)


def psi(baseline: np.ndarray, current: np.ndarray, *, n_bins: int = 10, eps: float = 1e-4) -> float:
    """PSI = sum((cur_i - base_i) * ln(cur_i / base_i)) over bins; NaN forms its own bin."""
    edges = psi_bins(baseline, n_bins)
    if edges.size == 0 and not np.isnan(baseline).any():
        return float("nan")

    def dist(v: np.ndarray) -> np.ndarray:
        finite = v[np.isfinite(v)]
        counts = np.bincount(
            np.searchsorted(edges, finite, side="right"), minlength=edges.size + 1
        ).astype(float)
        counts = np.append(counts, float(v.size - finite.size))  # NaN bin
        return counts / max(v.size, 1)

    p, q = dist(baseline), dist(current)
    p, q = np.clip(p, eps, None), np.clip(q, eps, None)
    return float(np.sum((q - p) * np.log(q / p)))


def verdict(max_psi: float, drop: bool) -> str:
    if max_psi >= PSI_REVIEW:
        return "review_new_model"
    if max_psi >= PSI_KEEP or drop:
        return "retrain"
    return "keep"


# --- run ---------------------------------------------------------------------------------------


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


def _local_month(df: pd.DataFrame) -> pd.Series:
    return (
        pd.to_datetime(df["hour_start"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.strftime("%Y-%m")
    )


def main(argv: list[str] | None = None) -> dict[str, Any]:
    ap = argparse.ArgumentParser(prog="experiments.retrain_gate", description=__doc__)
    ap.add_argument("--data-dir", type=Path, default=DATA_DIR)
    ap.add_argument(
        "--baseline-months",
        nargs="+",
        default=["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"],
    )
    ap.add_argument(
        "--drop-pct",
        type=float,
        default=5.0,
        help="WAPE worse than reference by more than this %% = drop",
    )
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ns = ap.parse_args(argv)
    t0 = time.perf_counter()

    model = load_promoted_model(HOLDOUT_DIR)
    pipe: Any = model.estimator
    feats, target = list(model.features), model.target
    assert pipe is not None, "promoted model not servable"
    trained_through = str(model.manifest.get("trained_through_hour"))
    holdout = json.loads((HOLDOUT_DIR / "h3_multiholdout.json").read_text(encoding="utf-8"))
    ref_wape = float(holdout["aggregate"]["wape"]["mean"])

    df, b1, files = load_usable_panel(ns.data_dir)
    month = _local_month(df)
    months = sorted(month.unique())
    base_mask = month.isin(ns.baseline_months).to_numpy()
    later = [m for m in months if m > max(ns.baseline_months)]
    x_all = df[feats].to_numpy(dtype=float)
    y_all = df[target].to_numpy(dtype=float)
    x_base = x_all[base_mask]

    # key features = the champion's own top-gain features (from the trees), capped at 12
    from experiments.shap_explain import tree_gain_importance

    gain, _ = tree_gain_importance(pipe.named_steps["model"], len(feats))
    key_idx = list(np.argsort(-gain)[:12])
    key_feats = [feats[i] for i in key_idx]

    # champion WAPE on the baseline span itself (in-sample for the champion) for context
    pred_base = pipe.predict(x_base)
    base_perf = {
        "rows": int(base_mask.sum()),
        "wape": wape(y_all[base_mask], pred_base),
        "mae": mae(y_all[base_mask], pred_base),
        "in_sample_for_champion": True,
    }

    monthly: list[dict[str, Any]] = []
    for m in later:
        cur = (month == m).to_numpy()
        x_cur, y_cur = x_all[cur], y_all[cur]
        psis = {feats[i]: psi(x_base[:, i], x_cur[:, i]) for i in range(len(feats))}
        key_psis = {f: psis[f] for f in key_feats}
        max_key = max(key_psis.values())
        pred = pipe.predict(x_cur)
        w = wape(y_cur, pred)
        rel = 100.0 * (w / ref_wape - 1.0)
        drop = rel > ns.drop_pct
        in_sample = m <= trained_through[:7]
        monthly.append(
            {
                "month": m,
                "rows": int(cur.sum()),
                "zones": int(df.loc[cur, "zone_id"].nunique()),
                "psi_key_features": {k: round(v, 4) for k, v in key_psis.items()},
                "psi_max_key": round(max_key, 4),
                "psi_max_key_feature": max(key_psis, key=lambda f: key_psis[f]),
                "psi_all_features_over_0_1": sorted([f for f, v in psis.items() if v >= PSI_KEEP]),
                "champion_wape": round(w, 4),
                "champion_mae": round(mae(y_cur, pred), 4),
                "champion_in_sample": in_sample,
                "wape_vs_reference_pct": round(rel, 2),
                "performance_drop": bool(drop),
                "verdict": verdict(max_key, drop),
            }
        )

    # challengers: for every flagged out-of-sample month, refit the champion's recipe on all rows
    # before that month (so the later months' challengers include the newest data) and compare
    # on that month. The first one (train ..07 -> eval 08) refits the champion's own span, which
    # makes it a refit-consistency check; the later ones add the recent months.
    challengers: list[dict[str, Any]] = []
    algo, params = model.manifest["algorithm"], dict(model.manifest["params"])
    for r in monthly:
        if r["verdict"] == "keep" or r["champion_in_sample"]:
            continue
        em = r["month"]
        train_mask = (month < em).to_numpy()
        cur = (month == em).to_numpy()
        chal, _grid = make_pipeline(algo)
        chal.set_params(**params, model__random_state=ns.seed)
        chal.fit(x_all[train_mask], y_all[train_mask])
        p_ch, p_cp = chal.predict(x_all[cur]), pipe.predict(x_all[cur])
        w_ch, w_cp = wape(y_all[cur], p_ch), wape(y_all[cur], p_cp)
        challengers.append(
            {
                "evaluation_month": em,
                "challenger_train_months": f"{months[0]}..{[mm for mm in months if mm < em][-1]}",
                "challenger_train_rows": int(train_mask.sum()),
                "includes_months_after_champion_span": [
                    mm for mm in months if mm < em and mm > trained_through[:7]
                ],
                "algorithm": algo,
                "params": params,
                "seed": ns.seed,
                "champion_wape": round(w_cp, 4),
                "challenger_wape": round(w_ch, 4),
                "champion_mae": round(mae(y_all[cur], p_cp), 4),
                "challenger_mae": round(mae(y_all[cur], p_ch), 4),
                "challenger_wape_rel_pct": round(100.0 * (w_ch / w_cp - 1.0), 2),
                "challenger_better": bool(w_ch < w_cp),
            }
        )
    challenger_note = (
        "champion = committed promoted model (fit through "
        + trained_through
        + "); challenger = same "
        "algorithm and params refit on all rows before the evaluation month"
    )

    result = {
        "experiment": "retrain_gate",
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(),
        "command": "python -m experiments.retrain_gate --baseline-months "
        + " ".join(ns.baseline_months)
        + f" --drop-pct {ns.drop_pct} --seed {ns.seed}",
        "seed": ns.seed,
        "data": {
            "source_files": files,
            "usable_rows": int(len(df)),
            "months": months,
            "baseline_months": ns.baseline_months,
        },
        "champion": {
            "run_id": model.manifest.get("run_id"),
            "algorithm": model.manifest.get("algorithm"),
            "trained_through_hour": trained_through,
            "feature_version": model.manifest.get("feature_version"),
        },
        "rule": {
            "psi_bins": "baseline deciles (10 bins, unique edges; value bins when <= 10 distinct values); NaN is its own bin",
            "psi_keep_below": PSI_KEEP,
            "psi_review_at_or_above": PSI_REVIEW,
            "performance_reference": {
                "wape": ref_wape,
                "source": "reports/v2/holdout/h3_multiholdout.json aggregate.wape.mean (May..Jul out-of-sample windows)",
            },
            "performance_drop_if_wape_worse_by_pct": ns.drop_pct,
            "key_features": key_feats,
            "key_features_rule": "top-12 total split gain of the champion's trees",
        },
        "baseline_performance": base_perf,
        "monthly": monthly,
        "challengers": challengers,
        "challenger_note": challenger_note,
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
        f"baseline {res['data']['baseline_months']}: rows {res['baseline_performance']['rows']} champion WAPE {res['baseline_performance']['wape']:.4f} (in-sample)"
    )
    print(
        f"reference WAPE {res['rule']['performance_reference']['wape']:.4f}; drop if worse by > {res['rule']['performance_drop_if_wape_worse_by_pct']}%"
    )
    print("key features:", res["rule"]["key_features"])
    print("\nmonth     rows   maxPSI(feature)              WAPE   vs ref   in-sample  verdict")
    for r in res["monthly"]:
        print(
            f"{r['month']}  {r['rows']:6d}  {r['psi_max_key']:.4f} ({r['psi_max_key_feature']:18s}) {r['champion_wape']:.4f}  {r['wape_vs_reference_pct']:+6.2f}%  {str(r['champion_in_sample']):5s}   {r['verdict']}"
        )
    for c in res["challengers"]:
        print(
            f"\nchallenger on {c['evaluation_month']}: champion WAPE {c['champion_wape']} vs challenger "
            f"{c['challenger_wape']} ({c['challenger_wape_rel_pct']:+.2f}%, train {c['challenger_train_months']}, "
            f"{c['challenger_train_rows']} rows, adds {c['includes_months_after_champion_span']}) -> better: {c['challenger_better']}"
        )
    if not res["challengers"]:
        print("\nno out-of-sample month flagged retrain/review -> no challenger fit")


if __name__ == "__main__":
    sys.exit(0 if main() else 1)

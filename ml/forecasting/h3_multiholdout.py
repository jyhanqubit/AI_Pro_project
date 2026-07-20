"""V2-01 — Measured Model Productization & H3 Multi-Holdout.

Runs the promoted forecasting model across several **rolling-origin** H3 (zone x local-hour)
holdout windows and writes a measured report plus a promoted-model manifest. This is the V2
answer to "a single lucky split": the same model is scored on >= 3 consecutive month-long test
windows, each trained only on data strictly before it (leakage-safe, section 5.2 / 11.3).

    python -m ml.forecasting.h3_multiholdout --data-dir data/raw/citibike
    make v2-holdout

Design (all real data, no fabrication):

1. **Promote** a measured model — GridSearchCV over a bounded algorithm pool on the development
   span *before the first test window only*, picking the best by cross-validated WAPE. Model
   selection therefore never sees any test window (no selection leakage).
2. **Evaluate** the promoted (algorithm, params) across the rolling windows: refit on each
   window's expanding training set, score WAPE / MAE / MASE / peak-direction on that window's
   test rows, against a seasonal-naive (B0) reference.
3. **Persist** the promoted model (refit on all usable data) + a manifest the serving layer
   reads in non-demo modes, and the multi-holdout metrics report.

The algorithm pool defaults to a tractable subset of the config zoo (``ridge``,
``hist_gradient_boosting``) so the run finishes in minutes on the full panel; ``--algos all``
opts into the complete zoo. The pool used is recorded in the report — the selection is measured
over whatever pool was actually run, and that pool is stated, never hidden.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.model_selection import GridSearchCV

from config.features import LOCAL_TZ, TARGET_PREFIX
from config.forecasting import CV_SPLITS, CV_TEST_HOURS, PRIMARY_TARGET, RANDOM_SEED
from ml.forecasting.baselines import seasonal_naive_predict
from ml.forecasting.dataset import Panel, load_real_panel
from ml.forecasting.experiment import usable_frame
from ml.forecasting.feature_selection import wape_scorer
from ml.forecasting.metrics import evaluate, mae
from ml.forecasting.models import algorithm_names, make_pipeline
from ml.forecasting.splits import rolling_origin_folds, to_hour_index

OUT_DIR = Path("reports/v2/holdout")
FEATURE_VERSION = "dfv1"  # leakage-safe demand+calendar feature set (B1)
# Default promotion pool: fast, strong, NaN-tolerant members of the config zoo. Keeps the full
# 210k-row run tractable; --algos all opts into the complete zoo.
DEFAULT_POOL = ("ridge", "hist_gradient_boosting")


def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_month(dt: datetime) -> datetime:
    total = dt.year * 12 + (dt.month - 1) + 1
    y, m = divmod(total, 12)
    return dt.replace(year=y, month=m + 1)


def build_monthly_windows(
    hours: pd.Series, n_windows: int, tz: str = LOCAL_TZ
) -> list[tuple[datetime, datetime]]:
    """The last ``n_windows`` whole calendar months present in the panel, as [start, end) bounds.

    Each window is a month-long test horizon; training is everything strictly before ``start``
    (expanding origin). The earliest month is skipped as training warm-up.
    """
    zone = ZoneInfo(tz)
    last = pd.Timestamp(hours.max()).to_pydatetime().astimezone(zone)
    first = pd.Timestamp(hours.min()).to_pydatetime().astimezone(zone)
    # Candidate test-month starts: from the second month present up to the last month present.
    months: list[datetime] = []
    cur = _add_month(_month_start(first))  # skip the first (partial/warm-up) month
    last_month_start = _month_start(last)
    while cur <= last_month_start:
        months.append(cur)
        cur = _add_month(cur)
    chosen = months[-n_windows:]
    return [(m, _add_month(m)) for m in chosen]


def bounded_holdout(
    hours: list[datetime], test_start: datetime, test_end: datetime
) -> tuple[np.ndarray, np.ndarray]:
    """Row positions for a rolling-origin window: train = hours < start, test = [start, end)."""
    h = np.array([pd.Timestamp(x).to_pydatetime() for x in hours], dtype=object)
    is_train = np.array([x < test_start for x in h], dtype=bool)
    is_test = np.array([test_start <= x < test_end for x in h], dtype=bool)
    return np.where(is_train)[0], np.where(is_test)[0]


def _matrix(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    return df[cols].to_numpy(dtype=float)


def promote_model(
    df: pd.DataFrame,
    b1_cols: list[str],
    target: str,
    first_test_start: datetime,
    pool: list[str],
) -> dict[str, Any]:
    """Select the best (algorithm, params) by CV WAPE on the pre-first-window development span.

    Model selection sees only rows strictly before the first test window, so no test window can
    leak into the promoted choice. Returns a manifest dict (no fit object).
    """
    hours = list(df["hour_start"])
    dev_pos = np.where(np.array([h < first_test_start for h in hours], dtype=bool))[0]
    if dev_pos.size == 0:
        raise ValueError("no development rows before the first test window")
    dev = df.iloc[dev_pos]
    hour_idx = to_hour_index(list(dev["hour_start"]))
    folds = rolling_origin_folds(hour_idx, CV_SPLITS, CV_TEST_HOURS)
    if not folds:
        raise ValueError("insufficient development span for rolling-origin CV")

    y_dev = dev[target].to_numpy(dtype=float)
    x_dev = _matrix(dev, b1_cols)

    leaderboard: dict[str, Any] = {}
    best_algo, best_params, best_cv = None, None, float("inf")
    for kind in pool:
        pipe, grid = make_pipeline(kind)
        search = GridSearchCV(
            pipe, grid, scoring=wape_scorer, cv=folds, refit=False, n_jobs=-1, error_score="raise"
        )
        search.fit(x_dev, y_dev)
        cv_wape = float(-search.best_score_)
        params = {k: _clean(v) for k, v in search.best_params_.items()}
        leaderboard[kind] = {"cv_wape": cv_wape, "best_params": params}
        if cv_wape < best_cv:
            best_algo, best_params, best_cv = kind, params, cv_wape

    return {
        "algorithm": best_algo,
        "params": best_params,
        "selection_cv_wape": best_cv,
        "selection_dev_rows": int(dev_pos.size),
        "selection_dev_last_hour": max(dev["hour_start"]).isoformat(),
        "pool": list(pool),
        "leaderboard": leaderboard,
        "feature_version": FEATURE_VERSION,
        "target": target,
    }


def _fit_promoted(algo: str, params: dict[str, Any]):
    pipe, _ = make_pipeline(algo)
    return clone(pipe).set_params(**params)


def evaluate_windows(
    df: pd.DataFrame,
    b1_cols: list[str],
    target: str,
    promoted: dict[str, Any],
    windows: list[tuple[datetime, datetime]],
) -> list[dict[str, Any]]:
    """Refit the promoted model per window (train strictly before test) and score H3 test rows."""
    prefix = TARGET_PREFIX[target]
    y = df[target].to_numpy(dtype=float)
    y_prev = df[f"{prefix}_lag_1"].to_numpy(dtype=float)
    x = _matrix(df, b1_cols)
    hours = list(df["hour_start"])

    out: list[dict[str, Any]] = []
    for i, (start, end) in enumerate(windows):
        train_pos, test_pos = bounded_holdout(hours, start, end)
        if train_pos.size == 0 or test_pos.size == 0:
            out.append({"window_id": i, "skipped": "empty train/test", "test_start": start.isoformat()})
            continue
        # Leakage guard: the latest training hour must be strictly before the test window.
        assert max(hours[p] for p in train_pos) < start, "train/test overlap — leakage!"

        y_train, y_test = y[train_pos], y[test_pos]
        # MASE denominator: in-sample seasonal-naive MAE on this window's training set.
        scale = mae(y_train, seasonal_naive_predict(df.iloc[train_pos], target))

        est = _fit_promoted(promoted["algorithm"], promoted["params"])
        est.fit(x[train_pos], y_train)
        pred = est.predict(x[test_pos])
        metrics = evaluate(y_test, pred, scale=scale, y_prev=y_prev[test_pos])

        b0_pred = seasonal_naive_predict(df.iloc[test_pos], target)
        b0 = evaluate(y_test, b0_pred, scale=scale)

        out.append(
            {
                "window_id": i,
                "test_start": start.isoformat(),
                "test_end": end.isoformat(),
                "train_end_hour": max(hours[p] for p in train_pos).isoformat(),
                "n_train": int(train_pos.size),
                "n_test": int(test_pos.size),
                "n_zones_test": int(df.iloc[test_pos]["zone_id"].nunique()),
                "seasonal_scale_mae": scale,
                "metrics": {
                    "wape": metrics["wape"],
                    "mae": metrics["mae"],
                    "mase": metrics["mase"],
                    "bias": metrics["bias"],
                    "peak_direction_accuracy": metrics.get("peak_direction_accuracy"),
                },
                "b0_seasonal_naive": {"wape": b0["wape"], "mae": b0["mae"], "mase": b0["mase"]},
            }
        )
    return out


def _agg(windows: list[dict[str, Any]], key: str) -> dict[str, float]:
    vals = [w["metrics"][key] for w in windows if "metrics" in w and np.isfinite(w["metrics"][key])]
    if not vals:
        return {"mean": float("nan"), "std": float("nan"), "n": 0}
    return {"mean": float(np.mean(vals)), "std": float(np.std(vals)), "n": len(vals)}


def _clean(v: Any) -> Any:
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    return str(v)


def _run_id(promoted: dict[str, Any], stamp: datetime) -> str:
    h = hashlib.sha1(
        json.dumps({"p": promoted["algorithm"], "params": promoted["params"]}, sort_keys=True).encode()
    ).hexdigest()[:8]
    return f"run_v2-01_{stamp.strftime('%Y%m%dT%H%M%SZ')}_{h}"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="ml.forecasting.h3_multiholdout")
    ap.add_argument("--data-dir", default="data/raw/citibike", help="dir of monthly trip archives")
    ap.add_argument("--target", default=PRIMARY_TARGET, choices=["departures", "arrivals", "net_flow"])
    ap.add_argument("--windows", type=int, default=3, help="number of rolling monthly holdout windows (>=3)")
    ap.add_argument("--algos", default=",".join(DEFAULT_POOL), help="promotion pool: comma list or 'all'")
    ns = ap.parse_args(argv)

    pool = algorithm_names() if ns.algos == "all" else [a.strip() for a in ns.algos.split(",") if a.strip()]
    stamp = datetime.now(UTC)

    print(f"V2-01 H3 multi-holdout — target={ns.target}, windows={ns.windows}, pool={pool}")
    panel: Panel = load_real_panel(Path(ns.data_dir))
    df = usable_frame(panel)
    if df.empty:
        raise SystemExit("no usable rows (need a real multi-month trip backfill)")
    print(f"usable rows={len(df)}  H3 zones={df['zone_id'].nunique()}  hours={df['hour_start'].nunique()}")

    windows = build_monthly_windows(df["hour_start"], ns.windows)
    if len(windows) < 3:
        raise SystemExit(f"only {len(windows)} monthly windows available; need >= 3 (add more months)")
    print("windows:", [(s.date().isoformat(), e.date().isoformat()) for s, e in windows])

    promoted = promote_model(df, panel.b1_cols, ns.target, windows[0][0], pool)
    print(f"promoted: {promoted['algorithm']} {promoted['params']} (CV WAPE={promoted['selection_cv_wape']:.4f})")

    per_window = evaluate_windows(df, panel.b1_cols, ns.target, promoted, windows)
    for w in per_window:
        if "metrics" in w:
            m = w["metrics"]
            print(
                f"  W{w['window_id']} {w['test_start'][:10]}..{w['test_end'][:10]}  "
                f"n_test={w['n_test']}  WAPE={m['wape']:.4f}  MAE={m['mae']:.3f}  "
                f"MASE={m['mase']:.4f}  (B0 WAPE={w['b0_seasonal_naive']['wape']:.4f})"
            )

    run_id = _run_id(promoted, stamp)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Persist the promoted model (refit on ALL usable data) for serving + a manifest.
    final_est = _fit_promoted(promoted["algorithm"], promoted["params"])
    final_est.fit(_matrix(df, panel.b1_cols), df[ns.target].to_numpy(dtype=float))
    model_path = OUT_DIR / "promoted_model.joblib"
    try:
        import joblib

        joblib.dump({"estimator": final_est, "features": list(panel.b1_cols), "target": ns.target}, model_path)
        model_saved = str(model_path)
    except Exception as exc:  # noqa: BLE001 — report, don't hide
        model_saved = f"unsaved ({exc!r})"

    manifest = {
        "run_id": run_id,
        "artifact_id": "reports/v2/holdout/promoted_model.json",
        "mode": "historical_replay",
        "claim_status": "measured",
        "freshness": stamp.isoformat(),
        "trained_on_rows": int(len(df)),
        "trained_through_hour": max(df["hour_start"]).isoformat(),
        "model_file": model_saved,
        **promoted,
    }
    (OUT_DIR / "promoted_model.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    report = {
        "run_id": run_id,
        "artifact_id": "reports/v2/holdout/h3_multiholdout.json",
        "mode": "historical_replay",
        "claim_status": "measured",
        "freshness": stamp.isoformat(),
        "grain": "h3_zone_x_local_hour",
        "target": ns.target,
        "seed": RANDOM_SEED,
        "split": "rolling_origin_expanding_monthly",
        "feature_version": FEATURE_VERSION,
        "promoted_model": {
            "algorithm": promoted["algorithm"],
            "params": promoted["params"],
            "selection_cv_wape": promoted["selection_cv_wape"],
            "pool": promoted["pool"],
        },
        "data_source": ns.data_dir,
        "usable_rows": int(len(df)),
        "h3_zones": int(df["zone_id"].nunique()),
        "windows": per_window,
        "aggregate": {
            "wape": _agg(per_window, "wape"),
            "mae": _agg(per_window, "mae"),
            "mase": _agg(per_window, "mase"),
        },
    }
    (OUT_DIR / "h3_multiholdout.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    agg = report["aggregate"]
    print(
        f"\naggregate over {agg['wape']['n']} windows: "
        f"WAPE {agg['wape']['mean']:.4f} ± {agg['wape']['std']:.4f}  |  "
        f"MASE {agg['mase']['mean']:.4f} ± {agg['mase']['std']:.4f}"
    )
    print(f"reports: {OUT_DIR}/h3_multiholdout.json, {OUT_DIR}/promoted_model.json")
    print("Done. Rolling-origin H3 multi-holdout; metrics are from executed fits only.")


if __name__ == "__main__":
    main()

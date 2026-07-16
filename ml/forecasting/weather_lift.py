"""Weather-feature predictive-lift runner (CLAUDE.md §5.4, §11, §22).

Measures whether adding weather-shock features to the demand+calendar baseline reduces holdout
error, with an explicit train/test split (e.g. train Jan-May, test June). Uses a single fast model
(HistGradientBoostingRegressor) instead of the GridSearch zoo so it stays tractable on a
multi-month panel, and the paired improvement is bootstrapped over day blocks (``predictive_lift``)
for an honest CI + verdict.

Leakage-safety (§5.4): weather features use the **previous day's** observed values (shifted), so no
future weather informs a past prediction. Weather is regional, so Central Park (NYC) daily weather
is a valid covariate for the nearby Jersey City demand panel (documented approximation).

    python -m ml.forecasting.weather_lift --data-dir data/raw/citibike \
        --weather data/fixtures/nyc_weather_2026h1.json --test-from 2026-06-01
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from config.features import LOCAL_TZ
from config.forecasting import PRIMARY_TARGET
from ml.forecasting.dataset import load_real_panel
from ml.forecasting.experiment import usable_frame
from ml.forecasting.metrics import mae, wape
from ml.forecasting.predictive_lift import run_predictive_lift
from ml.forecasting.splits import holdout_by_time

_WEATHER_COLS = (
    "w_prev_tmax",
    "w_prev_tmin",
    "w_prev_prcp",
    "w_prev_snow",
    "w_prev_awnd",
    "w_prev_snow_flag",
    "w_prev_freeze_flag",
    "w_prev_wet_flag",
)


def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def load_weather(path: Path) -> dict[str, dict[str, float]]:
    """Daily weather keyed by 'YYYY-MM-DD' (NOAA daily-summaries JSON)."""
    recs = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, float]] = {}
    for r in recs:
        out[r["DATE"]] = {
            "tmax": _f(r.get("TMAX")),
            "tmin": _f(r.get("TMIN")),
            "prcp": _f(r.get("PRCP")),
            "snow": _f(r.get("SNOW")),
            "awnd": _f(r.get("AWND")),
        }
    return out


def _prev_day_features(hour_start: datetime, weather: dict[str, dict[str, float]]) -> list[float]:
    """Leakage-safe weather features from the PREVIOUS local day (shifted, §5.4)."""
    key = (hour_start.date() - timedelta(days=1)).isoformat()
    w = weather.get(key)
    if w is None:
        return [float("nan")] * len(_WEATHER_COLS)
    snow, tmin, prcp = w["snow"], w["tmin"], w["prcp"]
    return [
        w["tmax"],
        tmin,
        prcp,
        snow,
        w["awnd"],
        1.0 if (snow == snow and snow > 0) else 0.0,  # snow_flag (NaN-safe)
        1.0 if (tmin == tmin and tmin < 32) else 0.0,  # freeze_flag (<32F)
        1.0 if (prcp == prcp and prcp > 0.1) else 0.0,  # wet_flag
    ]


def _fit_eval(
    x_dev: np.ndarray, y_dev: np.ndarray, x_test: np.ndarray, seed: int
) -> np.ndarray:
    model = HistGradientBoostingRegressor(random_state=seed, max_iter=300, learning_rate=0.05)
    model.fit(x_dev, y_dev)
    return np.clip(model.predict(x_test), 0.0, None)


def run(data_dir: str, weather_path: str, test_from: str, target: str = PRIMARY_TARGET) -> dict:
    tz = ZoneInfo(LOCAL_TZ)
    test_start = datetime.fromisoformat(test_from).replace(tzinfo=tz)
    weather = load_weather(Path(weather_path))

    print(f"loading panel from {data_dir} ...")
    panel = load_real_panel(Path(data_dir))
    df = usable_frame(panel)
    if df.empty:
        raise SystemExit("no usable rows (warm-up drop left nothing)")

    b1_cols = list(panel.b1_cols)
    # Append leakage-safe weather columns.
    wfeat = np.array([_prev_day_features(h, weather) for h in df["hour_start"]], dtype=float)
    for i, c in enumerate(_WEATHER_COLS):
        df[c] = wfeat[:, i]

    hours = list(df["hour_start"])
    dev_pos, test_pos = holdout_by_time(hours, test_start)
    if len(dev_pos) == 0 or len(test_pos) == 0:
        raise SystemExit(f"empty split at {test_from}: dev={len(dev_pos)} test={len(test_pos)}")

    y = df[target].to_numpy(dtype=float)
    x_b1 = df[b1_cols].to_numpy(dtype=float)
    x_bw = df[b1_cols + list(_WEATHER_COLS)].to_numpy(dtype=float)

    pred_b1 = _fit_eval(x_b1[dev_pos], y[dev_pos], x_b1[test_pos], seed=0)
    pred_bw = _fit_eval(x_bw[dev_pos], y[dev_pos], x_bw[test_pos], seed=0)
    y_test = y[test_pos]

    wape_b1, wape_bw = wape(y_test, pred_b1), wape(y_test, pred_bw)
    mae_b1, mae_bw = mae(y_test, pred_b1), mae(y_test, pred_bw)

    # Paired improvement CI, bootstrapped over day blocks (weather autocorrelates within a day).
    err0 = np.abs(y_test - pred_b1).tolist()
    err1 = np.abs(y_test - pred_bw).tolist()
    blocks = [h.date().toordinal() for h in np.array(hours, dtype=object)[test_pos]]
    lift = run_predictive_lift(err0, err1, blocks, coverage_ok=True)

    days = sorted({h.date().isoformat() for h in np.array(hours, dtype=object)[test_pos]})
    result = {
        "target": target,
        "n_train_rows": int(len(dev_pos)),
        "n_test_rows": int(len(test_pos)),
        "test_from": test_from,
        "test_days": f"{days[0]}..{days[-1]}" if days else None,
        "zones": int(df["zone_id"].nunique()),
        "baseline_demand_calendar": {"wape": round(wape_b1, 4), "mae": round(mae_b1, 4)},
        "plus_weather": {"wape": round(wape_bw, 4), "mae": round(mae_bw, 4)},
        "wape_abs_reduction": round(wape_b1 - wape_bw, 4),
        "wape_rel_reduction_pct": round(100 * (wape_b1 - wape_bw) / wape_b1, 2) if wape_b1 else 0.0,
        "predictive_lift": lift,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True, help="directory of trip archives (one panel)")
    ap.add_argument("--weather", required=True, help="NOAA daily-summaries JSON")
    ap.add_argument("--test-from", default="2026-06-01", help="local date; test = on/after it")
    ns = ap.parse_args(argv)

    res = run(ns.data_dir, ns.weather, ns.test_from)
    out = Path("reports/weather_lift.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")

    b1, bw, lift = res["baseline_demand_calendar"], res["plus_weather"], res["predictive_lift"]
    print(f"\ntrain rows={res['n_train_rows']}  test rows={res['n_test_rows']}  "
          f"zones={res['zones']}  test={res['test_days']}")
    print(f"B1  demand+calendar : WAPE={b1['wape']:.4f}  MAE={b1['mae']:.3f}")
    print(f"B1 + weather        : WAPE={bw['wape']:.4f}  MAE={bw['mae']:.3f}")
    print(f"WAPE reduction      : {res['wape_abs_reduction']:+.4f}  "
          f"({res['wape_rel_reduction_pct']:+.2f}% relative)")
    lo, hi = lift["ci_95"]
    print(f"paired lift verdict : {lift['verdict']}  mean_gain={lift['mean_gain']:.4f}  "
          f"CI95=[{lo:.4f}, {hi:.4f}]  (over {lift['n_blocks']} day-blocks)")
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

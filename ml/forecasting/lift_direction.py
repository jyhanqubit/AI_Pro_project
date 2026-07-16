"""Directional breakdown of the event-feature lift. CLAUDE.md §11, §22.

The headline event-feature lift (``ml.forecasting.borough_event_lift``) is a single aggregate WAPE/
MAE number. This asks a sharper question a reviewer cares about: *does the event feature help only
by predicting demand UP, or does it also correctly pull the forecast DOWN?*

For the June hold-out it compares the event-aware model (``pred_be``) to the demand+calendar
baseline (``pred_b1``) row by row, split by the direction the event feature moved the forecast and
by whether that improved accuracy. It reuses the same inputs and fit as ``borough_event_lift.run``
so the
overall MAE reconciles with the published headline (a printed check guards this). Numbers are
model-attributed, not causal; borough grain is a documented approximation of the H3 product grain.

Run: ``python -m ml.forecasting.lift_direction`` (streams the full trip history; minutes, not
seconds). Prints a reconciliation line plus per-direction accuracy — it makes no claim of its own
beyond what the measured rows show.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ml.forecasting.borough_event_lift import (
    _EVENT_COLS,
    _fit_eval,
    build_demand_features,
    build_event_index,
    stream_borough_cells,
)
from ml.forecasting.splits import holdout_by_time

_NY = ZoneInfo("America/New_York")
_DATA = "data/raw/citibike"
_EVENTS = "data/fixtures/nyc_permitted_events_filtered.jsonl.gz"
_TARGET = "departures"
_TEST_FROM = "2026-06-01"


def _block(
    name: str, m: np.ndarray, err0: np.ndarray, err1: np.ndarray, improved: np.ndarray
) -> None:
    n = int(m.sum())
    if n == 0:
        print(f"\n{name}: 0 rows")
        return
    imp = int((improved & m).sum())
    gain = float((err0[m] - err1[m]).mean())  # >0 => event model more accurate
    print(f"\n{name}: {n} rows")
    print(f"  improved accuracy: {imp}/{n} ({100 * imp / n:.1f}%)")
    print(f"  mean |err| reduction (baseline - events): {gain:+.3f}  (>0 = event model better)")


def main(argv: list[str] | None = None) -> int:
    test_start = datetime.fromisoformat(_TEST_FROM).replace(tzinfo=_NY)
    # Match borough_event_lift.run() (all zips) so the aggregate reconciles with the headline.
    paths = sorted(Path(_DATA).glob("*.zip"))
    print(f"aggregating {len(paths)} zip(s) ...", file=sys.stderr)
    rows = build_demand_features(stream_borough_cells(paths))
    events = build_event_index(Path(_EVENTS))

    b1_cols = sorted({k for r in rows for k in r.features})
    recs = []
    for r in rows:
        rec: dict[str, object] = {
            "borough": r.zone_id,
            "hour_start": r.hour_start,
            _TARGET: r.targets[_TARGET],
        }
        for k in b1_cols:
            rec[k] = r.features.get(k)
        hk = r.hour_start.strftime("%Y-%m-%d %H")
        ef = events.get((r.zone_id, hk))
        for c in _EVENT_COLS:
            rec[c] = ef[c] if ef else 0.0
        recs.append(rec)
    df = pd.DataFrame.from_records(recs)
    df = df.sort_values(["hour_start", "borough"]).reset_index(drop=True)
    for c in ("dep_lag_1", "dep_lag_24", "dep_lag_168", "dep_roll_mean_24"):
        if c in df.columns:
            df = df[df[c].notna()]
    df = df.reset_index(drop=True)

    hours = list(df["hour_start"])
    dev_pos, test_pos = holdout_by_time(hours, test_start)
    y = df[_TARGET].to_numpy(dtype=float)
    x_b1 = df[b1_cols].to_numpy(dtype=float)
    x_be = df[b1_cols + list(_EVENT_COLS)].to_numpy(dtype=float)
    pred_b1 = _fit_eval(x_b1[dev_pos], y[dev_pos], x_b1[test_pos], 0)
    pred_be = _fit_eval(x_be[dev_pos], y[dev_pos], x_be[test_pos], 0)
    yt = y[test_pos]

    err0 = np.abs(yt - pred_b1)
    err1 = np.abs(yt - pred_be)
    improved = err1 < err0
    delta = pred_be - pred_b1  # >0 event pushed UP, <0 event pushed DOWN
    ev_mask = df.loc[test_pos, list(_EVENT_COLS)].abs().sum(axis=1).to_numpy() > 0

    print("=" * 60)
    print(
        f"RECONCILE  n_test={len(yt)}  MAE baseline={err0.mean():.4f}  events={err1.mean():.4f}  "
        f"gain/row={err0.mean() - err1.mean():+.4f}"
    )
    print(f"June test rows: {len(yt)}  | event-window rows: {int(ev_mask.sum())}")

    up, down = delta > 0.5, delta < -0.5
    flat = ~(up | down)
    print("\n--- split by the direction the event feature moved the forecast ---")
    _block("Event pushed forecast UP   (pred_events > baseline)", up, err0, err1, improved)
    _block("Event pushed forecast DOWN (pred_events < baseline)", down, err0, err1, improved)
    _block("Event ~no change", flat, err0, err1, improved)

    demand_below = yt < pred_b1
    print("\n--- rows where actual demand came in BELOW the baseline forecast ---")
    _block("actual < baseline (demand dip)", demand_below, err0, err1, improved)
    _block("demand dip AND event pushed DOWN", demand_below & down, err0, err1, improved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

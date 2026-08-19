"""Borough-grain event predictive-lift runner (CLAUDE.md §5.4, §11, §22).

Measures whether NYC permitted-event features improve borough-hour demand forecasting, with an
explicit train/test split (train Jan-May, test June). Full-NYC H3-zone trips are too large for this
environment, so demand is aggregated to the coarser **borough × local hour** grain by STREAMING each
monthly trip zip row-by-row (bounded memory) and assigning each start point to its nearest borough
centroid (a documented approximation; no external geo data). Permitted events already carry a
borough, so they join at the same grain with no geocoding.

Leakage-safety (§5.4): demand lag/rolling features come from the shared leakage-safe builder; event
features use the public permit schedule (start/end times known in advance), counting only events
overlapping or imminent at the forecast hour — never future information that was not already public.

Model-attributed, not causal. A single fast model (HistGradientBoostingRegressor) is fit per feature
set and the paired improvement is bootstrapped over day blocks for an honest CI + verdict.

    python -m ml.forecasting.borough_event_lift \
        --data-dir data/raw/citibike \
        --events data/fixtures/nyc_permitted_events_filtered.jsonl.gz \
        --test-from 2026-06-01
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from config.forecasting import PRIMARY_TARGET
from contracts.demand import DemandCell
from contracts.enums import OperatingMode
from ml.forecasting.metrics import mae, wape
from ml.forecasting.predictive_lift import run_predictive_lift
from ml.forecasting.splits import holdout_by_time
from pipelines.features.lags import build_demand_features

_NY = ZoneInfo("America/New_York")

# Well-known borough centroids (lat, lng). Each trip start / event is assigned to the nearest one —
# a coarse, no-external-data approximation (documented). Manhattan dominates both trips and events.
_BOROUGH_CENTROIDS = {
    "Manhattan": (40.776, -73.971),
    "Brooklyn": (40.650, -73.950),
    "Queens": (40.728, -73.795),
    "Bronx": (40.837, -73.886),
    "Staten Island": (40.579, -74.150),
}
_B_ITEMS = list(_BOROUGH_CENTROIDS.items())

# Event types that draw crowds / reroute mobility (for a severity-style feature).
_CROWD_TYPES = {
    "parade",
    "street event",
    "block party",
    "farmers market",
    "sidewalk sale",
    "plaza partner event",
    "plaza event",
    "open street partner event",
    "open culture",
}


# --- Out-of-city rejection (added 2026-08-19 after a measured defect) -------------------------
# Nearest-centroid assignment has no notion of a city boundary: a New Jersey trip is silently
# handed to whichever NYC centroid happens to be closest. Feeding the Jersey City archives into
# this panel put ~110k JC/Hoboken trips into the NYC boroughs -- most into Manhattan, and enough
# into Staten Island (whose centroid is the only one west of the others) to fabricate 486 of the
# 720 June "Staten Island" hours. Those rows paired New Jersey demand with real NYC permit events
# and produced a spurious event lift. See docs/EVENT_LIFT_FINDINGS.md.
#
# The two guards below are empirical, not guessed (measured on 2026-06, 5.38M NYC + 110k JC trips):
#   * NYC trips west of the Hudson reach at most lat 40.6851 (Bay Ridge / Red Hook).
#   * Jersey City / Hoboken trips start at lat 40.6922.
# The 780 m gap between them is where the boundary is drawn, so the rule rejected 100% of JC trips
# and 0 NYC trips on that month.
_NJ_MIN_LAT = 40.688  # north of Staten Island / Bay Ridge...
_NJ_MAX_LNG = -74.020  # ...and west of the Hudson => New Jersey, not a borough.
# Second, independent net for gross misassignment from any other out-of-area source: NYC trips sit
# at most 8.6 km from their centroid, so 15 km rejects far-away points without touching real data.
_MAX_CENTROID_KM = 15.0
_KM_PER_DEG_LAT = 111.0
_KM_PER_DEG_LNG = 84.6  # at ~40.7 N

REJECT_IMPLAUSIBLE = "implausible_coords"
REJECT_NEW_JERSEY = "west_of_hudson_new_jersey"
REJECT_FAR_FROM_CENTROID = "far_from_any_centroid"


def borough_of(lat: float, lng: float, reasons: Counter[str] | None = None) -> str | None:
    """Nearest-centroid borough for a point (approximate), or None when the point is not NYC.

    Rejections are counted into ``reasons`` when given, so callers can report exclusions instead of
    dropping rows silently (section 6.1).
    """
    if not (40.0 < lat < 41.2 and -74.6 < lng < -73.4):
        if reasons is not None:
            reasons[REJECT_IMPLAUSIBLE] += 1
        return None
    if lat > _NJ_MIN_LAT and lng < _NJ_MAX_LNG:
        if reasons is not None:
            reasons[REJECT_NEW_JERSEY] += 1
        return None
    best, best_d = None, 1e9
    for name, (blat, blng) in _B_ITEMS:
        d = (lat - blat) ** 2 + (lng - blng) ** 2
        if d < best_d:
            best, best_d = name, d
    if best is not None:
        blat, blng = _BOROUGH_CENTROIDS[best]
        km = math.hypot((lat - blat) * _KM_PER_DEG_LAT, (lng - blng) * _KM_PER_DEG_LNG)
        if km > _MAX_CENTROID_KM:
            if reasons is not None:
                reasons[REJECT_FAR_FROM_CENTROID] += 1
            return None
    return best


def _hour_key(ts: str) -> tuple[str, datetime] | None:
    """'2026-06-30 16:58:39.826' -> ('2026-06-30 16', aware hour). Fast slice parse; None if bad."""
    if len(ts) < 13:
        return None
    try:
        y, mo, d, h = int(ts[0:4]), int(ts[5:7]), int(ts[8:10]), int(ts[11:13])
        return ts[:13], datetime(y, mo, d, h, tzinfo=_NY)
    except ValueError:
        return None


def stream_borough_cells(
    paths: list[Path], reasons: Counter[str] | None = None
) -> list[DemandCell]:
    """Stream trip zips -> departures/arrivals by (borough, local hour). Bounded memory.

    Trips outside NYC are rejected by ``borough_of`` and counted by reason; the tally is printed and
    also written into ``reasons`` when the caller supplies a counter (section 6.1: excluded rows are
    reported, never dropped silently).
    """
    rejected: Counter[str] = Counter() if reasons is None else reasons
    dep: Counter[tuple[str, str]] = Counter()
    arr: Counter[tuple[str, str]] = Counter()
    dep_mem: Counter[tuple[str, str]] = Counter()
    dep_cas: Counter[tuple[str, str]] = Counter()
    hour_by_key: dict[str, datetime] = {}
    n = 0

    for p in paths:
        with zipfile.ZipFile(p) as z:
            members = [
                m for m in z.namelist() if m.lower().endswith(".csv") and not m.startswith("__")
            ]
            for name in members:
                with z.open(name) as f:
                    reader = csv.reader(io.TextIOWrapper(f, "utf-8", "replace"))
                    header = next(reader, None)
                    if not header:
                        continue
                    ix = {c: i for i, c in enumerate(header)}
                    if not all(c in ix for c in ("started_at", "start_lat", "start_lng")):
                        continue
                    i_st, i_la, i_lo = ix["started_at"], ix["start_lat"], ix["start_lng"]
                    i_et = ix.get("ended_at")
                    i_ela, i_elo = ix.get("end_lat"), ix.get("end_lng")
                    i_mc = ix.get("member_casual")
                    for row in reader:
                        n += 1
                        try:
                            b = borough_of(float(row[i_la]), float(row[i_lo]), rejected)
                        except (ValueError, IndexError):
                            b = None
                        if b:
                            hk = _hour_key(row[i_st])
                            if hk:
                                key = (b, hk[0])
                                dep[key] += 1
                                hour_by_key[hk[0]] = hk[1]
                                if i_mc is not None and len(row) > i_mc:
                                    if row[i_mc] == "member":
                                        dep_mem[key] += 1
                                    elif row[i_mc] == "casual":
                                        dep_cas[key] += 1
                        # arrivals at destination borough
                        if i_et is not None and i_ela is not None and i_elo is not None:
                            try:
                                eb = borough_of(float(row[i_ela]), float(row[i_elo]))
                            except (ValueError, IndexError):
                                eb = None
                            if eb:
                                ehk = _hour_key(row[i_et])
                                if ehk:
                                    arr[(eb, ehk[0])] += 1
                                    hour_by_key[ehk[0]] = ehk[1]
    print(f"  streamed {n:,} trips -> {len(dep)} borough-hour departure cells", file=sys.stderr)
    if rejected:
        detail = ", ".join(f"{k}={v:,}" for k, v in sorted(rejected.items()))
        print(
            f"  rejected {sum(rejected.values()):,} out-of-city trips ({detail})", file=sys.stderr
        )

    cells: list[DemandCell] = []
    for key in dep.keys() | arr.keys():
        b, hkey = key
        d, a = dep.get(key, 0), arr.get(key, 0)
        cells.append(
            DemandCell(
                zone_id=b,
                hour_start=hour_by_key[hkey],
                departures=d,
                arrivals=a,
                net_flow=a - d,
                departures_member=dep_mem.get(key, 0),
                departures_casual=dep_cas.get(key, 0),
                mode=OperatingMode.HISTORICAL_REPLAY,
            )
        )
    cells.sort(key=lambda c: (c.hour_start, c.zone_id))
    return cells


def _parse_event_dt(s: str) -> datetime | None:
    hk = _hour_key(s.replace("T", " "))
    return hk[1] if hk else None


def build_event_index(events_path: Path) -> dict[tuple[str, str], dict[str, float]]:
    """(borough, 'YYYY-MM-DD HH') -> event feature counts, from the public permit schedule."""
    idx: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"ev_active": 0.0, "ev_closure": 0.0, "ev_crowd": 0.0, "ev_upcoming6h": 0.0}
    )
    opener = gzip.open if events_path.suffix == ".gz" else open
    kept = 0
    with opener(events_path, "rt", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            e = json.loads(line)
            b = (e.get("event_borough") or "").strip().title()
            if b not in _BOROUGH_CENTROIDS:
                continue
            start = _parse_event_dt(e.get("start_date_time") or "")
            end = _parse_event_dt(e.get("end_date_time") or "") or start
            if start is None:
                continue
            kept += 1
            etype = (e.get("event_type") or "").strip().lower()
            closure = (e.get("street_closure_type") or "N/A").strip().upper() != "N/A"
            crowd = etype in _CROWD_TYPES
            # Active hours (cap 48h so a multi-day permit cannot blow up).
            span_end = min(end, start + timedelta(hours=48)) if end else start
            h = start.replace(minute=0, second=0, microsecond=0)
            while h <= span_end:
                k = (b, h.strftime("%Y-%m-%d %H"))
                idx[k]["ev_active"] += 1
                if closure:
                    idx[k]["ev_closure"] += 1
                if crowd:
                    idx[k]["ev_crowd"] += 1
                h += timedelta(hours=1)
            # Imminent (known ahead): the 6 hours before start.
            for back in range(1, 7):
                k = (b, (start - timedelta(hours=back)).strftime("%Y-%m-%d %H"))
                idx[k]["ev_upcoming6h"] += 1
    print(f"  indexed {kept} events into borough-hour features", file=sys.stderr)
    return idx


_EVENT_COLS = ("ev_active", "ev_closure", "ev_crowd", "ev_upcoming6h")


def _fit_eval(x_dev, y_dev, x_test, seed: int) -> np.ndarray:
    m = HistGradientBoostingRegressor(random_state=seed, max_iter=300, learning_rate=0.05)
    m.fit(x_dev, y_dev)
    return np.clip(m.predict(x_test), 0.0, None)


def run(data_dir: str, events_path: str, test_from: str, target: str = PRIMARY_TARGET) -> dict:
    test_start = datetime.fromisoformat(test_from).replace(tzinfo=_NY)
    paths = sorted(Path(data_dir).glob("*.zip"))
    print(f"aggregating {len(paths)} trip zip(s) to borough-hour ...", file=sys.stderr)
    cells = stream_borough_cells(paths)
    rows = build_demand_features(cells)
    if not rows:
        raise SystemExit("no feature rows built")

    events = build_event_index(Path(events_path))

    # Assemble matrix: demand+calendar (B1) feature keys shared by rows.
    b1_cols = sorted({k for r in rows for k in r.features})
    import pandas as pd

    recs = []
    for r in rows:
        rec: dict[str, Any] = {
            "borough": r.zone_id,
            "hour_start": r.hour_start,
            target: r.targets[target],
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
    # Drop warm-up rows lacking the core lag features.
    for c in ("dep_lag_1", "dep_lag_24", "dep_lag_168", "dep_roll_mean_24"):
        if c in df.columns:
            df = df[df[c].notna()]
    df = df.reset_index(drop=True)

    hours = list(df["hour_start"])
    dev_pos, test_pos = holdout_by_time(hours, test_start)
    if len(dev_pos) == 0 or len(test_pos) == 0:
        raise SystemExit(f"empty split: dev={len(dev_pos)} test={len(test_pos)}")

    y = df[target].to_numpy(dtype=float)
    x_b1 = df[b1_cols].to_numpy(dtype=float)
    x_be = df[b1_cols + list(_EVENT_COLS)].to_numpy(dtype=float)
    pred_b1 = _fit_eval(x_b1[dev_pos], y[dev_pos], x_b1[test_pos], 0)
    pred_be = _fit_eval(x_be[dev_pos], y[dev_pos], x_be[test_pos], 0)
    y_test = y[test_pos]

    wape_b1, wape_be = wape(y_test, pred_b1), wape(y_test, pred_be)
    err0 = np.abs(y_test - pred_b1).tolist()
    err1 = np.abs(y_test - pred_be).tolist()
    blocks = [h.date().toordinal() for h in np.array(hours, dtype=object)[test_pos]]
    lift = run_predictive_lift(err0, err1, blocks, coverage_ok=True)

    # How many test rows actually carry an event signal (for honest event-window reading).
    ev_test = df.loc[test_pos, list(_EVENT_COLS)].abs().sum(axis=1).to_numpy() > 0
    days = sorted({h.date().isoformat() for h in np.array(hours, dtype=object)[test_pos]})

    # City-wide daily series over the test window: actual vs baseline vs +events (for plotting).
    test_hours = np.array(hours, dtype=object)[test_pos]
    by_day: dict[str, list[float]] = {}
    for i, hh in enumerate(test_hours):
        d = hh.date().isoformat()
        acc = by_day.setdefault(d, [0.0, 0.0, 0.0])
        acc[0] += float(y_test[i])
        acc[1] += float(pred_b1[i])
        acc[2] += float(pred_be[i])
    daily_series = [
        {
            "date": d,
            "actual": round(v[0], 1),
            "pred_b1": round(v[1], 1),
            "pred_events": round(v[2], 1),
        }
        for d, v in sorted(by_day.items())
    ]

    return {
        "grain": "borough-hour (nearest-centroid; approximate)",
        "target": target,
        "n_train_rows": int(len(dev_pos)),
        "n_test_rows": int(len(test_pos)),
        "test_rows_with_event": int(ev_test.sum()),
        "boroughs": sorted(df["borough"].unique().tolist()),
        "test_from": test_from,
        "test_days": f"{days[0]}..{days[-1]}" if days else None,
        "baseline_demand_calendar": {
            "wape": round(wape_b1, 4),
            "mae": round(mae(y_test, pred_b1), 4),
        },
        "plus_events": {"wape": round(wape_be, 4), "mae": round(mae(y_test, pred_be), 4)},
        "wape_abs_reduction": round(wape_b1 - wape_be, 4),
        "wape_rel_reduction_pct": round(100 * (wape_b1 - wape_be) / wape_b1, 2) if wape_b1 else 0.0,
        "predictive_lift": lift,
        "daily_series": daily_series,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--events", required=True, help="filtered permitted-events JSONL(.gz)")
    ap.add_argument("--test-from", default="2026-06-01")
    ns = ap.parse_args(argv)

    res = run(ns.data_dir, ns.events, ns.test_from)
    out = Path("reports/borough_event_lift.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")

    b1, be, lift = res["baseline_demand_calendar"], res["plus_events"], res["predictive_lift"]
    lo, hi = lift["ci_95"]
    print(f"\ngrain: {res['grain']}  boroughs={res['boroughs']}")
    print(
        f"train rows={res['n_train_rows']}  test rows={res['n_test_rows']}  "
        f"(with event signal: {res['test_rows_with_event']})  test={res['test_days']}"
    )
    print(f"B1  demand+calendar : WAPE={b1['wape']:.4f}  MAE={b1['mae']:.3f}")
    print(f"B1 + events         : WAPE={be['wape']:.4f}  MAE={be['mae']:.3f}")
    print(
        f"WAPE reduction      : {res['wape_abs_reduction']:+.4f}  "
        f"({res['wape_rel_reduction_pct']:+.2f}% relative)"
    )
    print(
        f"paired lift verdict : {lift['verdict']}  mean_gain={lift['mean_gain']:.4f}  "
        f"CI95=[{lo:.4f}, {hi:.4f}]  ({lift['n_blocks']} day-blocks)"
    )
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

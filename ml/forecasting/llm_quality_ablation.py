"""V2-03 — which QUALITY axis makes the permit feed work? A degradation ablation.

The density curve showed count is necessary but not sufficient (non-monotonic). This isolates the
other axes: take the FULL dense permit feed (all 63,070 events, +2.69%) and degrade ONE quality axis
at a time to news-like, holding density constant, measuring whether the permit value survives.

Degradations (each vs A0):
- full        : exact hour + exact borough + advance timing (control, should be +2.69%)
- coarse_time : event active a FLAT block over its whole day (loses the precise hour) — news-like time
- citywide    : event attributed to ALL boroughs (loses precise location) — news-like geography
- retro       : event known only AFTER it starts (available_at = end) — news-like retrospective timing

Whichever degradation collapses the value is a *necessary* quality axis — and exactly what news lacks.

Writes `reports/v2/llm_value/quality_ablation.json`.
"""

from __future__ import annotations

import argparse
import gzip
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from config.forecasting import PRIMARY_TARGET
from ml.forecasting.borough_event_lift import (
    _BOROUGH_CENTROIDS,
    _CROWD_TYPES,
    _EVENT_COLS,
    _fit_eval,
    _parse_event_dt,
    stream_borough_cells,
)
from ml.forecasting.llm_feature_value import llm_feature_value
from ml.forecasting.metrics import wape
from ml.forecasting.splits import holdout_by_time
from pipelines.features.lags import build_demand_features

_NY = ZoneInfo("America/New_York")
OUT_DIR = Path("reports/v2/llm_value")
MODES = ("full", "coarse_time", "citywide", "retro")


def _permit_events(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def build_index(events_path: Path, mode: str) -> dict:
    """Permit borough-hour features under one degradation mode (density always full)."""
    idx = defaultdict(lambda: {c: 0.0 for c in _EVENT_COLS})
    for e in _permit_events(events_path):
        b = (e.get("event_borough") or "").strip().title()
        if b not in _BOROUGH_CENTROIDS:
            continue
        start = _parse_event_dt(e.get("start_date_time") or "")
        end = _parse_event_dt(e.get("end_date_time") or "") or start
        if start is None:
            continue
        etype = (e.get("event_type") or "").strip().lower()
        closure = (e.get("street_closure_type") or "N/A").strip().upper() != "N/A"
        crowd = etype in _CROWD_TYPES
        boroughs = [b] if mode != "citywide" else list(_BOROUGH_CENTROIDS)

        if mode == "coarse_time":
            day = start.replace(hour=0, minute=0, second=0, microsecond=0)
            span = [(day + timedelta(hours=k)) for k in range(24)]           # flat over the day
        else:
            span_end = min(end, start + timedelta(hours=48)) if end else start
            h = start.replace(minute=0, second=0, microsecond=0)
            span = []
            while h <= span_end:
                span.append(h)
                h += timedelta(hours=1)

        for bb in boroughs:
            for hh in span:
                k = (bb, hh.strftime("%Y-%m-%d %H"))
                idx[k]["ev_active"] += 1
                if closure:
                    idx[k]["ev_closure"] += 1
                if crowd:
                    idx[k]["ev_crowd"] += 1
        # ev_upcoming6h: forward-looking (6h before start). In retro mode the event is known only
        # after it starts, so there is NO advance signal — skip the upcoming feature entirely.
        if mode != "retro":
            for back in range(1, 7):
                hk = (start - timedelta(hours=back)).strftime("%Y-%m-%d %H")
                for bb in boroughs:
                    idx[(bb, hk)]["ev_upcoming6h"] += 1
    return idx


def run(data_dir, events_path, test_from, target=PRIMARY_TARGET):
    test_start = datetime.fromisoformat(test_from).replace(tzinfo=_NY)
    paths = sorted(Path(data_dir).glob("*.zip"))
    if not paths:
        raise SystemExit(f"no trip zips in {data_dir}")
    rows = build_demand_features(stream_borough_cells(paths))
    b1_cols = sorted({k for r in rows for k in r.features})
    base = [{"borough": r.zone_id, "hour_start": r.hour_start, target: r.targets[target],
             **{k: r.features.get(k) for k in b1_cols}} for r in rows]
    base_df = pd.DataFrame.from_records(base)

    results = []
    for mode in MODES:
        idx = build_index(Path(events_path), mode)
        df = base_df.copy()
        for c in _EVENT_COLS:
            df[c] = [idx.get((b, h.strftime("%Y-%m-%d %H")), {}).get(c, 0.0)
                     for b, h in zip(df["borough"], df["hour_start"], strict=True)]
        d = df.sort_values(["hour_start", "borough"]).reset_index(drop=True)
        for c in ("dep_lag_1", "dep_lag_24", "dep_lag_168", "dep_roll_mean_24"):
            if c in d.columns:
                d = d[d[c].notna()]
        d = d.reset_index(drop=True)
        hours = list(d["hour_start"])
        dev_pos, test_pos = holdout_by_time(hours, test_start)
        y = d[target].to_numpy(dtype=float)
        p0 = _fit_eval(d[b1_cols].to_numpy(dtype=float)[dev_pos], y[dev_pos], d[b1_cols].to_numpy(dtype=float)[test_pos], 0)
        cc = b1_cols + list(_EVENT_COLS)
        p1 = _fit_eval(d[cc].to_numpy(dtype=float)[dev_pos], y[dev_pos], d[cc].to_numpy(dtype=float)[test_pos], 0)
        y_test = y[test_pos]
        blocks = [h.date().toordinal() for h in np.array(hours, dtype=object)[test_pos]]
        active = d.loc[test_pos, list(_EVENT_COLS)].abs().sum(axis=1).to_numpy() > 0
        lfv = llm_feature_value(y_test, p0, p1, active, blocks)
        results.append({"mode": mode, "wape_A0": round(float(wape(y_test, p0)), 4),
                        "wape_A1": round(float(wape(y_test, p1)), 4),
                        "active_bh": int(active.sum()), "decision": lfv["decision"],
                        "skill_pct": lfv["llm_active_skill_pct"], "ci95": lfv["active_error_gain_ci95"]})

    return {
        "run_id": f"run_v2-03quality_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/llm_value/quality_ablation.json",
        "mode": "historical_replay", "claim_status": "measured", "freshness": datetime.now(UTC).isoformat(),
        "grain": "borough-hour", "target": target, "test_from": test_from,
        "controls": "density held at FULL (all permit events); one quality axis degraded per mode",
        "modes": {r["mode"]: r for r in results},
        "note": "full is the control (+2.69%). A degradation that collapses the value is a necessary "
                "quality axis. coarse_time = news-like time; citywide = news-like location; retro = "
                "news-like retrospective availability.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ml.forecasting.llm_quality_ablation")
    ap.add_argument("--data-dir", default="data/raw/nyc")
    ap.add_argument("--events", default="data/fixtures/nyc_permitted_events_filtered.jsonl.gz")
    ap.add_argument("--test-from", default="2026-05-01")
    ns = ap.parse_args(argv)
    res = run(ns.data_dir, ns.events, ns.test_from)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "quality_ablation.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    print("PERMIT QUALITY DEGRADATION (density held FULL; degrade one axis to news-like)")
    print(f"  {'mode':12s} {'active_bh':>9s} {'WAPE_A0':>8s} {'WAPE_A1':>8s}  {'permit A1-A0':>18s}")
    for m in MODES:
        r = res["modes"][m]
        print(f"  {m:12s} {r['active_bh']:>9d} {r['wape_A0']:>8.4f} {r['wape_A1']:>8.4f}  "
              f"{r['decision'][:16]:>16s} {str(r['skill_pct'])+'%':>10s}")
    print(f"report -> {OUT_DIR}/quality_ablation.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

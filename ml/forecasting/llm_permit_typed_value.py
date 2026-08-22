"""V2-03 (A, corrected) — LLM structures event-type FACTS; the model learns the demand response.

Attempt 1 (`llm_permit_enrich_value.py`) had the LLM impose a demand DIRECTION and hurt (−3.39%),
because an unvalidated prior overrides what the model would learn. The correct division of labor
(V2 contract: "the LLM does not directly compute demand"): the LLM categorizes each permit's free
text into a TYPE bucket (a fact); the model learns each bucket's demand response from data.

So instead of one aggregate `ev_active` count, disaggregate into per-bucket active counts — the LLM's
factual structuring — with NO sign imposed:

    A1_crude   b1 + [ev_active, ev_crowd, ev_closure, ev_upcoming6h]   (aggregate count baseline)
    A1_typed   b1 + [ev_closure, ev_upcoming6h] + per-bucket active counts

If A1_typed beats A1_crude on WAPE, the LLM's semantic *categorization* (letting the model learn that
parades behave differently from film shoots) adds measured value — without the LLM guessing demand.

Writes `reports/v2/llm_value/permit_typed_contribution.json`.
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
    _EVENT_COLS,
    _fit_eval,
    _parse_event_dt,
    build_event_index,
    stream_borough_cells,
)
from ml.forecasting.llm_feature_value import llm_feature_value
from ml.forecasting.metrics import mae, wape
from ml.forecasting.splits import holdout_by_time
from pipelines.features.lags import build_demand_features

_NY = ZoneInfo("America/New_York")
OUT_DIR = Path("reports/v2/llm_value")

# LLM factual categorization of the 20 permit event types into demand-relevant buckets (NO sign).
_BUCKET = {
    "Parade": "surge", "Athletic Race / Tour": "surge", "Street Festival": "surge",
    "Single Block Festival": "surge",
    "Block Party": "gather", "Street Event": "gather", "Plaza Partner Event": "gather",
    "Plaza Event": "gather", "Open Culture": "gather", "Open Street Partner Event": "openstreet",
    "Farmers Market": "market", "Sidewalk Sale": "market", "Health Fair": "market",
    "Production Event": "production",
    "Religious Event": "civic", "Stationary Demonstration": "civic", "Press Conference": "civic",
    "Clean-Up": "civic", "Miscellaneous": "civic", "Stickball": "civic",
}
BUCKETS = ("surge", "gather", "openstreet", "market", "production", "civic")
TYPED_COLS = tuple(f"ev_{b}" for b in BUCKETS) + ("ev_closure", "ev_upcoming6h")


def build_typed_index(events_path: Path):
    idx = defaultdict(lambda: {c: 0.0 for c in TYPED_COLS})
    opener = gzip.open if events_path.suffix == ".gz" else open
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
            bucket = _BUCKET.get((e.get("event_type") or "").strip(), "civic")
            closure = (e.get("street_closure_type") or "N/A").strip().upper() != "N/A"
            span_end = min(end, start + timedelta(hours=48)) if end else start
            h = start.replace(minute=0, second=0, microsecond=0)
            while h <= span_end:
                cell = idx[(b, h.strftime("%Y-%m-%d %H"))]
                cell[f"ev_{bucket}"] += 1
                if closure:
                    cell["ev_closure"] += 1
                h += timedelta(hours=1)
            for back in range(1, 7):
                idx[(b, (start - timedelta(hours=back)).strftime("%Y-%m-%d %H"))]["ev_upcoming6h"] += 1
    return idx


def run(data_dir, events_path, test_from, target=PRIMARY_TARGET):
    test_start = datetime.fromisoformat(test_from).replace(tzinfo=_NY)
    paths = sorted(Path(data_dir).glob("*.zip"))
    if not paths:
        raise SystemExit(f"no trip zips in {data_dir}")
    rows = build_demand_features(stream_borough_cells(paths))
    crude = build_event_index(Path(events_path))
    typed = build_typed_index(Path(events_path))

    b1 = sorted({k for r in rows for k in r.features})
    recs = []
    for r in rows:
        rec = {"borough": r.zone_id, "hour_start": r.hour_start, target: r.targets[target]}
        for k in b1:
            rec[k] = r.features.get(k)
        hk = r.hour_start.strftime("%Y-%m-%d %H")
        ce = crude.get((r.zone_id, hk))
        for c in _EVENT_COLS:
            rec[c] = ce[c] if ce else 0.0
        te = typed.get((r.zone_id, hk))
        for c in TYPED_COLS:
            rec[c] = te[c] if te else 0.0
        recs.append(rec)
    df = pd.DataFrame.from_records(recs).sort_values(["hour_start", "borough"]).reset_index(drop=True)
    for c in ("dep_lag_1", "dep_lag_24", "dep_lag_168", "dep_roll_mean_24"):
        if c in df.columns:
            df = df[df[c].notna()]
    df = df.reset_index(drop=True)

    hours = list(df["hour_start"])
    dev, test = holdout_by_time(hours, test_start)
    y = df[target].to_numpy(dtype=float)
    cols = {
        "A0_demand_calendar": b1,
        "A1_crude_counts": b1 + list(_EVENT_COLS),
        "A1_typed_buckets": b1 + list(TYPED_COLS),
    }
    preds = {a: _fit_eval(df[cc].to_numpy(dtype=float)[dev], y[dev], df[cc].to_numpy(dtype=float)[test], 0)
             for a, cc in cols.items()}
    y_test = y[test]
    blocks = [h.date().toordinal() for h in np.array(hours, dtype=object)[test]]
    active = df.loc[test, list(_EVENT_COLS)].abs().sum(axis=1).to_numpy() > 0

    arms = {a: {"wape": round(float(wape(y_test, p)), 4), "mae": round(float(mae(y_test, p)), 3)}
            for a, p in preds.items()}
    typed_vs_crude = llm_feature_value(y_test, preds["A1_crude_counts"], preds["A1_typed_buckets"], active, blocks)
    typed_vs_a0 = llm_feature_value(y_test, preds["A0_demand_calendar"], preds["A1_typed_buckets"], active, blocks)

    return {
        "run_id": f"run_v2-03permittyped_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/llm_value/permit_typed_contribution.json",
        "mode": "historical_replay", "claim_status": "measured", "freshness": datetime.now(UTC).isoformat(),
        "grain": "borough-hour", "target": target, "test_from": test_from,
        "buckets": list(BUCKETS),
        "llm_role": "factual categorization of permit event_type into demand-relevant buckets (NO "
                    "demand sign imposed); the model learns each bucket's response from data",
        "n_train_rows": int(len(dev)), "n_test_rows": int(len(test)), "test_active_cells": int(active.sum()),
        "arms": arms,
        "typed_vs_A0": typed_vs_a0,
        "typed_vs_crude": typed_vs_crude,
        "note": "typed disaggregation vs the aggregate count: does letting the model learn per-type "
                "responses (LLM structures the type facts) beat lumping all permits into one count?",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ml.forecasting.llm_permit_typed_value")
    ap.add_argument("--data-dir", default="data/raw/nyc")
    ap.add_argument("--events", default="data/fixtures/nyc_permitted_events_filtered.jsonl.gz")
    ap.add_argument("--test-from", default="2026-05-01")
    ns = ap.parse_args(argv)
    res = run(ns.data_dir, ns.events, ns.test_from)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "permit_typed_contribution.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    print(f"train={res['n_train_rows']} test={res['n_test_rows']} active={res['test_active_cells']}")
    for a, s in res["arms"].items():
        print(f"  {a:20s} WAPE={s['wape']:.4f}")
    for key, lbl in (("typed_vs_A0", "typed vs A0"), ("typed_vs_crude", "typed vs crude count")):
        m = res[key]
        print(f"  {lbl:22s}: {m['decision']}  skill={m['llm_active_skill_pct']}%  CI={m['active_error_gain_ci95']}")
    print(f"report -> {OUT_DIR}/permit_typed_contribution.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

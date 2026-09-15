"""V2-03 diagnostic — "how can MORE information reduce accuracy?"

The intuition is right: for an ideal learner more features can never hurt (it could ignore them).
The observed harm from LLM enrichment/type-splitting must therefore be an ESTIMATION effect, not an
information one. This checks it directly by reporting TRAIN vs TEST error for each arm.

Prediction if it is overfitting: adding features LOWERS train WAPE (the info is there and helps FIT)
but RAISES test WAPE (the finite tree fits train noise in the extra columns). A gradient-boosted tree
does not silently ignore useless features — it greedily splits on any column that lowers train loss,
including noise.

Arms: A0 (demand+calendar) / A1_crude (aggregate permit count) / A1_typed (6 per-type bucket counts).
Reports train and test WAPE + n_features for each. Writes `reports/v2/llm_value/overfit_diagnostic.json`.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from config.forecasting import PRIMARY_TARGET
from ml.forecasting.borough_event_lift import _EVENT_COLS, _fit_eval, build_event_index, stream_borough_cells
from ml.forecasting.llm_permit_typed_value import TYPED_COLS, build_typed_index
from ml.forecasting.metrics import wape
from ml.forecasting.splits import holdout_by_time
from pipelines.features.lags import build_demand_features

_NY = ZoneInfo("America/New_York")
OUT_DIR = Path("reports/v2/llm_value")


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

    arms = {"A0_demand_calendar": b1, "A1_crude_count": b1 + list(_EVENT_COLS),
            "A1_typed_buckets": b1 + list(TYPED_COLS)}
    out = {}
    for name, cc in arms.items():
        x = df[cc].to_numpy(dtype=float)
        p_train = _fit_eval(x[dev], y[dev], x[dev], 0)
        p_test = _fit_eval(x[dev], y[dev], x[test], 0)
        out[name] = {"n_features": len(cc),
                     "train_wape": round(float(wape(y[dev], p_train)), 4),
                     "test_wape": round(float(wape(y[test], p_test)), 4),
                     "generalization_gap": round(float(wape(y[test], p_test) - wape(y[dev], p_train)), 4)}

    return {
        "run_id": f"run_v2-03overfit_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/llm_value/overfit_diagnostic.json",
        "mode": "historical_replay", "claim_status": "measured", "freshness": datetime.now(UTC).isoformat(),
        "target": target, "test_from": test_from, "n_train": int(len(dev)), "n_test": int(len(test)),
        "arms": out,
        "reading": "If train_wape falls as features are added (info helps fit) while test_wape for the "
                   "richer arm rises above the simpler arm, the harm is OVERFITTING/estimation, not a "
                   "loss of information — the info is present but not usably estimable from this data.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ml.forecasting.llm_overfit_diagnostic")
    ap.add_argument("--data-dir", default="data/raw/nyc")
    ap.add_argument("--events", default="data/fixtures/nyc_permitted_events_filtered.jsonl.gz")
    ap.add_argument("--test-from", default="2026-05-01")
    ns = ap.parse_args(argv)
    res = run(ns.data_dir, ns.events, ns.test_from)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "overfit_diagnostic.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"{'arm':22s} {'#feat':>6s} {'TRAIN wape':>11s} {'TEST wape':>10s} {'gap':>8s}")
    for a, r in res["arms"].items():
        print(f"  {a:20s} {r['n_features']:>6d} {r['train_wape']:>11.4f} {r['test_wape']:>10.4f} {r['generalization_gap']:>8.4f}")
    print(f"report -> {OUT_DIR}/overfit_diagnostic.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""V2-03 (A) — LLM semantic enrichment of the REAL forward-looking permit feed.

The permit feed already satisfies the four conditions (dense, precise-time, precise-location,
forward-looking) and lifts WAPE +2.69% via crude COUNT features (ev_active, ev_crowd, ...). But a
count treats a parade, a farmers market, and a film shoot identically — it carries no DIRECTION and
no SCALE. That is exactly what an LLM reading the free-text event type/name can add.

This is the honest realization of "an LLM structures a forward-looking source into the A1 slot",
using REAL data (no fabrication): the in-session LLM assigns each permit a signed ``demand_effect``
(surge > 0 / suppress < 0) and a ``scale`` from its event type + closure extent + name keywords. The
mapping below IS that judgment — deterministic and committed for audit (like the V2-03 news
extraction). We then compare:

    A0            demand + calendar
    A1_crude      + crude permit COUNT features (the current +2.69% source)
    A1_enriched   + LLM signed/scaled permit features (direction + magnitude)

If A1_enriched beats A1_crude on WAPE, the LLM's *semantic* structuring of the real forward-looking
source adds measured value the counts miss — a MEASURED LLM contribution, not simulated.

Writes `reports/v2/llm_value/permit_enrich_contribution.json`.
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
ENRICH_COLS = ("permit_demand_signal", "permit_surge", "permit_suppress")

# In-session LLM semantic judgment: event_type -> (signed demand_effect for BIKE demand, base scale).
# Reasoning is per type; committed for audit. Surge = draws riders to/through the area; suppress =
# takes the roadway/lanes and deters riding (filming, construction closures).
_TYPE_EFFECT = {
    "Parade": (0.40, 1.0), "Athletic Race / Tour": (0.45, 1.0), "Street Festival": (0.35, 0.9),
    "Single Block Festival": (0.30, 0.7), "Block Party": (0.25, 0.6), "Street Event": (0.20, 0.6),
    "Open Street Partner Event": (0.30, 0.7), "Plaza Partner Event": (0.15, 0.5),
    "Plaza Event": (0.15, 0.5), "Farmers Market": (0.20, 0.6), "Sidewalk Sale": (0.05, 0.3),
    "Religious Event": (0.10, 0.4), "Health Fair": (0.10, 0.4), "Open Culture": (0.20, 0.5),
    "Stationary Demonstration": (0.30, 0.6), "Stickball": (0.05, 0.2), "Clean-Up": (0.0, 0.2),
    "Press Conference": (0.0, 0.2), "Miscellaneous": (0.0, 0.3),
    "Production Event": (-0.30, 0.7),   # filming: takes curb/street, deters riding -> suppress
}
_NAME_BOOST = {  # free-text name keywords the LLM would weight up
    "marathon": (0.10, 0.5), "bike tour": (0.15, 0.5), "5k": (0.05, 0.3), "10k": (0.05, 0.3),
    "half marathon": (0.10, 0.4), "festival": (0.05, 0.2), "concert": (0.10, 0.3),
}
_CLOSURE_SCALE = {  # closure extent scales the magnitude
    "Full Street Closure": 1.0, "Full Sidewalk Closure": 0.6, "Sidewalk and Street Closure": 1.0,
    "Sidewalk and Curb Lane Closure": 0.7, "Curb Lane Only": 0.5, "Partial Sidewalk Closure": 0.4,
    "Pedestrian Plaza": 0.6, "N/A": 0.5,
}


def _effect(e: dict) -> tuple[float, float]:
    etype = (e.get("event_type") or "").strip()
    eff, scale = _TYPE_EFFECT.get(etype, (0.1, 0.4))
    name = (e.get("event_name") or "").lower()
    for kw, (de, ds) in _NAME_BOOST.items():
        if kw in name:
            eff += de
            scale = max(scale, ds)
    closure = (e.get("street_closure_type") or "N/A").strip()
    scale *= _CLOSURE_SCALE.get(closure, 0.5)
    return max(-1.0, min(1.0, eff)), scale


def build_enriched_index(events_path: Path):
    """(borough,'YYYY-MM-DD HH') -> signed/scaled permit features from LLM semantic judgment."""
    idx = defaultdict(lambda: {c: 0.0 for c in ENRICH_COLS})
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
            eff, scale = _effect(e)
            signal = eff * scale
            span_end = min(end, start + timedelta(hours=48)) if end else start
            h = start.replace(minute=0, second=0, microsecond=0)
            while h <= span_end:
                cell = idx[(b, h.strftime("%Y-%m-%d %H"))]
                cell["permit_demand_signal"] += signal
                cell["permit_surge"] += max(signal, 0.0)
                cell["permit_suppress"] += max(-signal, 0.0)
                h += timedelta(hours=1)
    return idx


def run(data_dir, events_path, test_from, target=PRIMARY_TARGET):
    test_start = datetime.fromisoformat(test_from).replace(tzinfo=_NY)
    paths = sorted(Path(data_dir).glob("*.zip"))
    if not paths:
        raise SystemExit(f"no trip zips in {data_dir}")
    rows = build_demand_features(stream_borough_cells(paths))
    crude = build_event_index(Path(events_path))
    enriched = build_enriched_index(Path(events_path))

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
        en = enriched.get((r.zone_id, hk))
        for c in ENRICH_COLS:
            rec[c] = en[c] if en else 0.0
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
        "A1_llm_enriched": b1 + list(_EVENT_COLS) + list(ENRICH_COLS),
    }
    preds = {a: _fit_eval(df[cc].to_numpy(dtype=float)[dev], y[dev], df[cc].to_numpy(dtype=float)[test], 0)
             for a, cc in cols.items()}
    y_test = y[test]
    blocks = [h.date().toordinal() for h in np.array(hours, dtype=object)[test]]
    active = df.loc[test, list(_EVENT_COLS)].abs().sum(axis=1).to_numpy() > 0

    arms = {a: {"wape": round(float(wape(y_test, p)), 4), "mae": round(float(mae(y_test, p)), 3)}
            for a, p in preds.items()}
    enrich_vs_crude = llm_feature_value(y_test, preds["A1_crude_counts"], preds["A1_llm_enriched"], active, blocks)
    crude_vs_a0 = llm_feature_value(y_test, preds["A0_demand_calendar"], preds["A1_crude_counts"], active, blocks)
    enriched_vs_a0 = llm_feature_value(y_test, preds["A0_demand_calendar"], preds["A1_llm_enriched"], active, blocks)

    return {
        "run_id": f"run_v2-03permitenrich_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/llm_value/permit_enrich_contribution.json",
        "mode": "historical_replay", "claim_status": "measured", "freshness": datetime.now(UTC).isoformat(),
        "grain": "borough-hour", "target": target, "test_from": test_from,
        "source": "REAL NYC permit feed (satisfies all 4 conditions); LLM adds signed direction + scale",
        "llm_enrichment": "in-session semantic judgment: event_type + closure + name-keywords -> "
                          "(signed demand_effect, scale); committed in this module for audit",
        "n_train_rows": int(len(dev)), "n_test_rows": int(len(test)),
        "test_active_cells": int(active.sum()),
        "arms": arms,
        "crude_counts_vs_A0": crude_vs_a0,
        "llm_enriched_vs_A0": enriched_vs_a0,
        "llm_enrichment_value_vs_crude": enrich_vs_crude,
        "note": "The source is real and forward-looking; the LLM contribution is the SEMANTIC "
                "structuring (direction+magnitude) that crude counts lack. enrich_vs_crude is the "
                "measured incremental LLM value on top of the counting baseline.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ml.forecasting.llm_permit_enrich_value")
    ap.add_argument("--data-dir", default="data/raw/nyc")
    ap.add_argument("--events", default="data/fixtures/nyc_permitted_events_filtered.jsonl.gz")
    ap.add_argument("--test-from", default="2026-05-01")
    ns = ap.parse_args(argv)
    res = run(ns.data_dir, ns.events, ns.test_from)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "permit_enrich_contribution.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    print(f"train={res['n_train_rows']} test={res['n_test_rows']} active={res['test_active_cells']}")
    for a, s in res["arms"].items():
        print(f"  {a:22s} WAPE={s['wape']:.4f}")
    for key, lbl in (("crude_counts_vs_A0", "crude counts vs A0"),
                     ("llm_enriched_vs_A0", "LLM-enriched vs A0"),
                     ("llm_enrichment_value_vs_crude", "LLM enrichment vs crude")):
        m = res[key]
        print(f"  {lbl:26s}: {m['decision']}  skill={m['llm_active_skill_pct']}%  CI={m['active_error_gain_ci95']}")
    print(f"report -> {OUT_DIR}/permit_enrich_contribution.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

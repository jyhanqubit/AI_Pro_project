"""V2-03 — news as a POST-PROCESSING correction, with per-mechanism (n-dimensional) factors.

Two ideas, combined:

1. **Post-processing, not a feature.** Feeding news into the tree failed because the model won't
   trust a sparse feature and the autoregressive lags dominate. Instead, run the base model (A1) and
   then *correct its output*: ``pred_corrected = pred_base + Σ_channel α_channel · signal_channel``.
   The factors ``α`` are calibrated on the TRAIN residuals and applied to TEST — an honest
   out-of-sample "post-processing factor", the thing practitioners actually tune.

2. **n-dimensional / context.** The effect is not one scalar. Split the LLM's signed demand signal
   into mechanism channels — weather-suppression, gathering/venue surge, transit substitution, safety
   — and fit a SEPARATE α per channel. Each channel's sign/size is learned from how that mechanism's
   events actually moved demand, so "transit shutdown → surge" and "blizzard → suppression" get
   different corrections.

Calibration caveat: α is fit on in-sample dev residuals (the base model already fit the dev events),
so α is biased toward 0 — a conservative estimate. If a nonzero α still helps TEST, the value is
real; α ≈ 0 is consistent with the redundancy finding. Reports the fitted factors + test effect.

Writes `reports/v2/llm_value/postprocess_contribution.json`.
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
from ml.forecasting.event_features_v2 import EventFeatureCfg, build_signed_demand_index
from ml.forecasting.llm_feature_value import llm_feature_value
from ml.forecasting.metrics import mae, wape
from ml.forecasting.splits import holdout_by_time
from pipelines.collectors import NewsFixtureCollector
from pipelines.features.lags import build_demand_features

_NY = ZoneInfo("America/New_York")
OUT_DIR = Path("reports/v2/llm_value")
# mechanism channels (n-dimensional context): each fits its own post-processing factor
CHANNELS = {
    "weather": {"WEATHER_SHOCK", "ROAD_CLOSURE"},
    "gather": {"PUBLIC_GATHERING", "LARGE_VENUE_EVENT"},
    "transit": {"TRANSIT_DISRUPTION"},
    "safety": {"SAFETY_INCIDENT"},
}


def _events(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def run(data_dir, events_path, news_path, signed_events, test_from, target=PRIMARY_TARGET):
    test_start = datetime.fromisoformat(test_from).replace(tzinfo=_NY)
    paths = sorted(Path(data_dir).glob("*.zip"))
    if not paths:
        raise SystemExit(f"no trip zips in {data_dir}")
    rows = build_demand_features(stream_borough_cells(paths))
    permitted = build_event_index(Path(events_path))
    articles = {a.article_id: a for a in NewsFixtureCollector(Path(news_path)).collect().records}
    all_events = _events(Path(signed_events))
    # per-channel signed signal indices
    chan_idx = {ch: build_signed_demand_index([e for e in all_events if e.get("event_type") in types],
                                              articles, EventFeatureCfg())[0]
                for ch, types in CHANNELS.items()}

    b1_cols = sorted({k for r in rows for k in r.features})
    recs = []
    for r in rows:
        rec = {"borough": r.zone_id, "hour_start": r.hour_start, target: r.targets[target]}
        for k in b1_cols:
            rec[k] = r.features.get(k)
        hk = r.hour_start.strftime("%Y-%m-%d %H")
        pe = permitted.get((r.zone_id, hk))
        for c in _EVENT_COLS:
            rec[c] = pe[c] if pe else 0.0
        for ch in CHANNELS:
            cell = chan_idx[ch].get((r.zone_id, hk))
            rec[f"sig_{ch}"] = float(cell["news_demand_signal"]) if cell else 0.0
        recs.append(rec)
    df = pd.DataFrame.from_records(recs).sort_values(["hour_start", "borough"]).reset_index(drop=True)
    for c in ("dep_lag_1", "dep_lag_24", "dep_lag_168", "dep_roll_mean_24"):
        if c in df.columns:
            df = df[df[c].notna()]
    df = df.reset_index(drop=True)

    hours = list(df["hour_start"])
    dev_pos, test_pos = holdout_by_time(hours, test_start)
    y = df[target].to_numpy(dtype=float)
    base_cols = b1_cols + list(_EVENT_COLS)
    x = df[base_cols].to_numpy(dtype=float)
    pred_dev = _fit_eval(x[dev_pos], y[dev_pos], x[dev_pos], 0)    # in-sample dev preds (to calibrate)
    pred_test = _fit_eval(x[dev_pos], y[dev_pos], x[test_pos], 0)  # out-of-sample test preds
    y_dev, y_test = y[dev_pos], y[test_pos]

    sig_cols = [f"sig_{ch}" for ch in CHANNELS]
    S_dev = df.loc[dev_pos, sig_cols].to_numpy(dtype=float)
    S_test = df.loc[test_pos, sig_cols].to_numpy(dtype=float)

    # Calibrate per-channel factors on dev residuals: resid_dev ≈ S_dev @ alpha  (least squares).
    resid_dev = y_dev - pred_dev
    dev_active = np.abs(S_dev).sum(axis=1) > 0
    if dev_active.sum() >= len(sig_cols):
        alpha, *_ = np.linalg.lstsq(S_dev[dev_active], resid_dev[dev_active], rcond=None)
    else:
        alpha = np.zeros(len(sig_cols))
    factors = {ch: round(float(a), 3) for ch, a in zip(CHANNELS, alpha, strict=True)}

    pred_test_corr = pred_test + S_test @ alpha
    blocks = [h.date().toordinal() for h in np.array(hours, dtype=object)[test_pos]]
    active = np.abs(S_test).sum(axis=1) > 0

    arms = {"A1_base": {"wape": round(float(wape(y_test, pred_test)), 4), "mae": round(float(mae(y_test, pred_test)), 3)},
            "A1_postprocessed": {"wape": round(float(wape(y_test, pred_test_corr)), 4),
                                 "mae": round(float(mae(y_test, pred_test_corr)), 3)}}
    lfv = llm_feature_value(y_test, pred_test, pred_test_corr, active, blocks)

    return {
        "run_id": f"run_v2-03postproc_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/llm_value/postprocess_contribution.json",
        "mode": "historical_replay", "claim_status": "measured", "freshness": datetime.now(UTC).isoformat(),
        "grain": "borough-hour", "target": target, "test_from": test_from,
        "n_train_rows": int(len(dev_pos)), "n_test_rows": int(len(test_pos)),
        "method": "post-processing: pred_corrected = pred_base + sum_channel alpha_channel * signal_channel; "
                  "alpha calibrated on dev residuals (in-sample, conservative), applied out-of-sample to test",
        "calibrated_factors": factors,
        "dev_active_cells": int(dev_active.sum()), "test_active_cells": int(active.sum()),
        "arms": arms,
        "postprocess_value_vs_base": lfv,
        "calibration_caveat": "alpha is fit on in-sample dev residuals so it is biased toward 0 "
                              "(conservative); a nonzero alpha that still helps test is real value, "
                              "alpha~0 is consistent with lag-redundancy.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ml.forecasting.llm_postprocess_value")
    ap.add_argument("--data-dir", default="data/raw/nyc")
    ap.add_argument("--events", default="data/fixtures/nyc_permitted_events_filtered.jsonl.gz")
    ap.add_argument("--news", default="data/fixtures/news_live/news_gdelt_nyc_2026h1.jsonl")
    ap.add_argument("--signed-events", default="data/fixtures/news_live/claude_events_signed_2026h1.jsonl")
    ap.add_argument("--test-from", default="2026-05-01")
    ns = ap.parse_args(argv)
    res = run(ns.data_dir, ns.events, ns.news, ns.signed_events, ns.test_from)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "postprocess_contribution.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    print(f"train={res['n_train_rows']} test={res['n_test_rows']} "
          f"dev_active={res['dev_active_cells']} test_active={res['test_active_cells']}")
    print("\nCALIBRATED per-mechanism post-processing factors (fit on train residuals):")
    for ch, a in res["calibrated_factors"].items():
        print(f"  alpha[{ch:8s}] = {a:+.3f}")
    for a, s in res["arms"].items():
        print(f"  {a:18s} WAPE={s['wape']:.4f}")
    lfv = res["postprocess_value_vs_base"]
    print(f"POST-PROCESS value vs base: {lfv['decision']}  skill={lfv['llm_active_skill_pct']}%  "
          f"CI={lfv['active_error_gain_ci95']} (n={lfv['n_llm_active_rows']})")
    print(f"report -> {OUT_DIR}/postprocess_contribution.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

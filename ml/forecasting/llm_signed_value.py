"""V2-03 — SIGNED LLM demand signal: let the LLM say the DIRECTION (storm -> down, festival -> up,
transit shutdown -> up via substitution), not just "how newsworthy".

The importance-weight arm failed because it was unsigned (always amplify), so a blizzard boosted the
prediction the wrong way. This arm uses the LLM's ``demand_effect`` in [-1,+1] to build a SIGNED
feature `news_demand_signal = demand_effect * severity * decay`. The model gets the sign FROM the LLM
instead of learning it from ~19 sparse events — the whole point of using an LLM.

Arms: A1 (permit) vs A1 + news_demand_signal. LFV on the signal-active subset.
Writes `reports/v2/llm_value/signed_demand_contribution.json`.
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
from ml.forecasting.event_features_v2 import SIGNED_COLS, EventFeatureCfg, build_signed_demand_index
from ml.forecasting.llm_feature_value import llm_feature_value
from ml.forecasting.metrics import mae, wape
from ml.forecasting.splits import holdout_by_time
from pipelines.collectors import NewsFixtureCollector
from pipelines.features.lags import build_demand_features

_NY = ZoneInfo("America/New_York")
OUT_DIR = Path("reports/v2/llm_value")


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
    sig_idx, sig_diag = build_signed_demand_index(_events(Path(signed_events)), articles, EventFeatureCfg())

    b1_cols = sorted({k for r in rows for k in r.features})
    recs, examples = [], []
    for r in rows:
        rec = {"borough": r.zone_id, "hour_start": r.hour_start, target: r.targets[target]}
        for k in b1_cols:
            rec[k] = r.features.get(k)
        hk = r.hour_start.strftime("%Y-%m-%d %H")
        pe = permitted.get((r.zone_id, hk))
        for c in _EVENT_COLS:
            rec[c] = pe[c] if pe else 0.0
        se = sig_idx.get((r.zone_id, hk))
        rec["news_demand_signal"] = float(se["news_demand_signal"]) if se else 0.0
        recs.append(rec)
        if rec["news_demand_signal"] != 0.0:
            examples.append((r.zone_id, hk, round(rec["news_demand_signal"], 3), float(r.targets[target])))
    df = pd.DataFrame.from_records(recs).sort_values(["hour_start", "borough"]).reset_index(drop=True)
    for c in ("dep_lag_1", "dep_lag_24", "dep_lag_168", "dep_roll_mean_24"):
        if c in df.columns:
            df = df[df[c].notna()]
    df = df.reset_index(drop=True)

    hours = list(df["hour_start"])
    dev_pos, test_pos = holdout_by_time(hours, test_start)
    y = df[target].to_numpy(dtype=float)
    cols = {"A1_plus_permitted": b1_cols + list(_EVENT_COLS),
            "A_plus_signed_demand": b1_cols + list(_EVENT_COLS) + list(SIGNED_COLS)}
    preds = {a: _fit_eval(df[cc].to_numpy(dtype=float)[dev_pos], y[dev_pos],
                          df[cc].to_numpy(dtype=float)[test_pos], 0) for a, cc in cols.items()}
    y_test = y[test_pos]
    blocks = [h.date().toordinal() for h in np.array(hours, dtype=object)[test_pos]]
    active = df.loc[test_pos, "news_demand_signal"].to_numpy() != 0.0

    arms = {a: {"wape": round(float(wape(y_test, p)), 4), "mae": round(float(mae(y_test, p)), 3)}
            for a, p in preds.items()}
    lfv = llm_feature_value(y_test, preds["A1_plus_permitted"], preds["A_plus_signed_demand"], active, blocks)

    # sign-correctness check: on active TEST cells, does the signed signal agree with the actual
    # demand deviation from each cell's own seasonal-naive lag? (honest sanity, not used in the model)
    tp = np.array(test_pos)
    sig_test = df.loc[test_pos, "news_demand_signal"].to_numpy()
    lag = df.loc[test_pos, "dep_lag_168"].to_numpy() if "dep_lag_168" in df.columns else None
    sign_hits = None
    if lag is not None:
        m = sig_test != 0.0
        dev = y_test[m] - lag[m]                    # actual deviation vs same-hour-last-week
        agree = np.sign(dev) == np.sign(sig_test[m])
        sign_hits = {"n": int(m.sum()), "sign_agreement": round(float(agree.mean()), 3) if m.sum() else None}

    return {
        "run_id": f"run_v2-03signed_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/llm_value/signed_demand_contribution.json",
        "mode": "historical_replay", "claim_status": "measured", "freshness": datetime.now(UTC).isoformat(),
        "grain": "borough-hour", "target": target, "test_from": test_from,
        "n_train_rows": int(len(dev_pos)), "n_test_rows": int(len(test_pos)),
        "signed_diag": sig_diag, "test_rows_signal_active": int(active.sum()),
        "example_signed_values": [{"borough": b, "hour": h, "news_demand_signal": s, "actual_departures": d}
                                  for b, h, s, d in sorted(examples, key=lambda e: e[1])[:10]],
        "sign_correctness_vs_seasonal_naive": sign_hits,
        "arms": arms,
        "signed_demand_value_vs_A1": lfv,
        "note": "news_demand_signal = LLM demand_effect (signed) x severity x decay. Direction comes "
                "from the LLM (blizzard<0, festival/substitution>0), not learned from sparse data.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ml.forecasting.llm_signed_value")
    ap.add_argument("--data-dir", default="data/raw/nyc")
    ap.add_argument("--events", default="data/fixtures/nyc_permitted_events_filtered.jsonl.gz")
    ap.add_argument("--news", default="data/fixtures/news_live/news_gdelt_nyc_2026h1.jsonl")
    ap.add_argument("--signed-events", default="data/fixtures/news_live/claude_events_signed_2026h1.jsonl")
    ap.add_argument("--test-from", default="2026-05-01")
    ns = ap.parse_args(argv)
    res = run(ns.data_dir, ns.events, ns.news, ns.signed_events, ns.test_from)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "signed_demand_contribution.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    print(f"train={res['n_train_rows']} test={res['n_test_rows']} signal_active={res['test_rows_signal_active']} "
          f"(leakage_dropped={res['signed_diag']['leakage_dropped']})")
    print("\nEXAMPLE signed signals in test (May) — negative=suppress, positive=surge:")
    for e in res["example_signed_values"]:
        print(f"  {e['borough']+' '+e['hour']:26s} signal={e['news_demand_signal']:+.3f}  actual_dep={e['actual_departures']:.0f}")
    sc = res["sign_correctness_vs_seasonal_naive"]
    if sc:
        print(f"\nsign agreement vs seasonal-naive deviation: {sc['sign_agreement']} (n={sc['n']})")
    for a, s in res["arms"].items():
        print(f"  {a:24s} WAPE={s['wape']:.4f}")
    lfv = res["signed_demand_value_vs_A1"]
    print(f"SIGNED demand value vs A1: {lfv['decision']}  skill={lfv['llm_active_skill_pct']}%  "
          f"CI={lfv['active_error_gain_ci95']} (n={lfv['n_llm_active_rows']})")
    print(f"report -> {OUT_DIR}/signed_demand_contribution.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

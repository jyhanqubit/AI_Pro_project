"""V2-03 — does the event/news layer add value at an OPERATIONAL forecast horizon?

The news-null was a nowcasting artifact: with `dep_lag_1` (last hour) available, autoregression
captures an ongoing event and the event features are redundant. But rebalancing needs lead time —
you forecast hours/a day ahead, when recent lags are NOT yet known. At horizon H, a feature that
references hour (target − k) is knowable only if k ≥ H, so at H=24 the model loses `lag_1` and every
rolling/momentum feature (they use the most recent hours). Forward-looking event knowledge should
then carry real information the stale lags lack.

This sweeps horizons and, at each, refits A0 / A1(+permit) / A2(+signed news) using only
horizon-legal features, reporting the LLM Feature Value of the permit layer (A1−A0) and the news
layer (A2−A1). If event value grows with horizon, the layer earns its keep where it is actually used.

Writes `reports/v2/llm_value/horizon_contribution.json`.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from config.forecasting import PRIMARY_TARGET
from ml.forecasting.borough_event_lift import _EVENT_COLS, _fit_eval, build_event_index, stream_borough_cells
from ml.forecasting.event_features_v2 import SIGNED_COLS, EventFeatureCfg, build_signed_demand_index
from ml.forecasting.llm_feature_value import llm_feature_value
from ml.forecasting.metrics import wape
from ml.forecasting.splits import holdout_by_time
from pipelines.collectors import NewsFixtureCollector
from pipelines.features.lags import build_demand_features

_NY = ZoneInfo("America/New_York")
OUT_DIR = Path("reports/v2/llm_value")
HORIZONS = (1, 6, 24, 48)
_LAG_RE = re.compile(r"lag_(\d+)$")


def usable_at_horizon(col: str, h: int) -> bool:
    """A feature knowable when forecasting h hours ahead (references only hours <= target-h)."""
    if "roll" in col or "momentum" in col or "mom_" in col:
        return h == 1                       # rolling/momentum use the most recent hour(s)
    m = _LAG_RE.search(col)
    if m:
        return int(m.group(1)) >= h         # lag_k known iff k >= h
    return True                             # calendar/static features are always known


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
    sig_idx, _ = build_signed_demand_index(_events(Path(signed_events)), articles, EventFeatureCfg())

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
        se = sig_idx.get((r.zone_id, hk))
        rec["news_demand_signal"] = float(se["news_demand_signal"]) if se else 0.0
        recs.append(rec)
    df = pd.DataFrame.from_records(recs).sort_values(["hour_start", "borough"]).reset_index(drop=True)
    for c in ("dep_lag_1", "dep_lag_24", "dep_lag_168", "dep_roll_mean_24"):
        if c in df.columns:
            df = df[df[c].notna()]
    df = df.reset_index(drop=True)

    hours = list(df["hour_start"])
    dev_pos, test_pos = holdout_by_time(hours, test_start)
    y = df[target].to_numpy(dtype=float)
    y_test = y[test_pos]
    blocks = [h.date().toordinal() for h in np.array(hours, dtype=object)[test_pos]]
    news_active = df.loc[test_pos, "news_demand_signal"].to_numpy() != 0.0
    permit_active = df.loc[test_pos, list(_EVENT_COLS)].abs().sum(axis=1).to_numpy() > 0

    def fit(cols):
        x = df[cols].to_numpy(dtype=float)
        return _fit_eval(x[dev_pos], y[dev_pos], x[test_pos], 0)

    by_h = []
    for h in HORIZONS:
        base = [c for c in b1_cols if usable_at_horizon(c, h)]
        p0 = fit(base)
        p1 = fit(base + list(_EVENT_COLS))
        p2 = fit(base + list(_EVENT_COLS) + list(SIGNED_COLS))
        permit_lfv = llm_feature_value(y_test, p0, p1, permit_active, blocks)
        news_lfv = llm_feature_value(y_test, p1, p2, news_active, blocks)
        by_h.append({
            "horizon_h": h, "n_base_features": len(base),
            "wape": {"A0": round(float(wape(y_test, p0)), 4),
                     "A1_permit": round(float(wape(y_test, p1)), 4),
                     "A2_news": round(float(wape(y_test, p2)), 4)},
            "permit_value_A1_minus_A0": {"decision": permit_lfv["decision"],
                                         "skill_pct": permit_lfv["llm_active_skill_pct"],
                                         "ci95": permit_lfv["active_error_gain_ci95"]},
            "news_value_A2_minus_A1": {"decision": news_lfv["decision"],
                                       "skill_pct": news_lfv["llm_active_skill_pct"],
                                       "ci95": news_lfv["active_error_gain_ci95"]},
        })

    return {
        "run_id": f"run_v2-03horizon_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/llm_value/horizon_contribution.json",
        "mode": "historical_replay", "claim_status": "measured", "freshness": datetime.now(UTC).isoformat(),
        "grain": "borough-hour", "target": target, "test_from": test_from,
        "n_train_rows": int(len(dev_pos)), "n_test_rows": int(len(test_pos)),
        "test_rows_permit_active": int(permit_active.sum()),
        "test_rows_news_active": int(news_active.sum()),
        "by_horizon": by_h,
        "note": "At horizon h only features referencing hours <= target-h are usable (lag_k with "
                "k>=h; no rolling/momentum for h>1). Tests whether the event/news layer's value grows "
                "as recent-demand autoregression becomes unavailable — the operational forecasting "
                "regime rebalancing needs.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ml.forecasting.llm_horizon_value")
    ap.add_argument("--data-dir", default="data/raw/nyc")
    ap.add_argument("--events", default="data/fixtures/nyc_permitted_events_filtered.jsonl.gz")
    ap.add_argument("--news", default="data/fixtures/news_live/news_gdelt_nyc_2026h1.jsonl")
    ap.add_argument("--signed-events", default="data/fixtures/news_live/claude_events_signed_2026h1.jsonl")
    ap.add_argument("--test-from", default="2026-05-01")
    ns = ap.parse_args(argv)
    res = run(ns.data_dir, ns.events, ns.news, ns.signed_events, ns.test_from)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "horizon_contribution.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    print(f"train={res['n_train_rows']} test={res['n_test_rows']} "
          f"permit_active={res['test_rows_permit_active']} news_active={res['test_rows_news_active']}")
    print(f"\n{'horizon':>7s} {'#feat':>6s} {'WAPE_A0':>8s} {'WAPE_A1':>8s} {'WAPE_A2':>8s}  "
          f"{'permit A1-A0':>26s}  {'news A2-A1':>26s}")
    for r in res["by_horizon"]:
        w = r["wape"]; p = r["permit_value_A1_minus_A0"]; n = r["news_value_A2_minus_A1"]
        print(f"{r['horizon_h']:>6d}h {r['n_base_features']:>6d} {w['A0']:>8.4f} {w['A1_permit']:>8.4f} "
              f"{w['A2_news']:>8.4f}  {p['decision'][:14]:>14s} {str(p['skill_pct'])+'%':>11s}  "
              f"{n['decision'][:14]:>14s} {str(n['skill_pct'])+'%':>11s}")
    print(f"report -> {OUT_DIR}/horizon_contribution.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

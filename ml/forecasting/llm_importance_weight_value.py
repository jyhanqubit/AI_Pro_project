"""V2-03 (a) — news as an IMPORTANCE WEIGHT on the dense permit feed, not a standalone feature.

The refutation showed the permit feed's value is DENSITY (63,070 events → a learnable coefficient),
and that adding sparse news as its own confident features injects noise. This arm keeps the dense
permit signal intact and lets news only MODULATE it:

    news_salience[b,h] = news importance in that borough-hour (severity x decay, availability-gated)
    ev_active_newswt   = ev_active * (1 + news_salience)     # permit activity, amplified if newsworthy
    ev_crowd_newswt    = ev_crowd  * (1 + news_salience)

Where there is no news (almost everywhere) salience=0 ⇒ weight x1.0 ⇒ the permit feature is
UNCHANGED. So this can only reweight the ~hundreds of news-active permit borough-hours; it can never
corrupt the dense base signal. That is the whole point: permits give volume, news gives "which of
these many permit events is a big deal".

Arms: A1 (permit) vs A1 + {news_salience, ev_active_newswt, ev_crowd_newswt}. LFV on the news-active
subset. Writes `reports/v2/llm_value/importance_weight_contribution.json`.
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
from ml.forecasting.event_features_v2 import EventFeatureCfg, build_permitized_index
from ml.forecasting.llm_feature_value import llm_feature_value
from ml.forecasting.metrics import mae, wape
from ml.forecasting.splits import holdout_by_time
from pipelines.collectors import NewsFixtureCollector
from pipelines.features.lags import build_demand_features

_NY = ZoneInfo("America/New_York")
OUT_DIR = Path("reports/v2/llm_value")
_WT_COLS = ("news_salience", "ev_active_newswt", "ev_crowd_newswt")


def _events(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def run(data_dir, events_path, news_path, perm_events, test_from, target=PRIMARY_TARGET):
    test_start = datetime.fromisoformat(test_from).replace(tzinfo=_NY)
    paths = sorted(Path(data_dir).glob("*.zip"))
    if not paths:
        raise SystemExit(f"no trip zips in {data_dir}")
    rows = build_demand_features(stream_borough_cells(paths))
    permitted = build_event_index(Path(events_path))
    articles = {a.article_id: a for a in NewsFixtureCollector(Path(news_path)).collect().records}
    # salience = news importance per borough-hour (precise, availability-gated); reuse the permitized
    # builder's decayed severity as the salience scalar.
    sal_idx, _ = build_permitized_index(_events(Path(perm_events)), articles, EventFeatureCfg())

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
        sal = sal_idx.get((r.zone_id, hk))
        s = float(sal["news_llm_severity"]) if sal else 0.0
        rec["news_salience"] = s
        rec["ev_active_newswt"] = rec["ev_active"] * (1.0 + s)
        rec["ev_crowd_newswt"] = rec["ev_crowd"] * (1.0 + s)
        recs.append(rec)
        if s > 0 and rec["ev_active"] > 0:  # collect real co-occurrence examples to show
            examples.append({"borough": r.zone_id, "hour": hk, "ev_active": rec["ev_active"],
                             "ev_crowd": rec["ev_crowd"], "news_salience": round(s, 3),
                             "ev_active_newswt": round(rec["ev_active_newswt"], 3)})
    df = pd.DataFrame.from_records(recs).sort_values(["hour_start", "borough"]).reset_index(drop=True)
    for c in ("dep_lag_1", "dep_lag_24", "dep_lag_168", "dep_roll_mean_24"):
        if c in df.columns:
            df = df[df[c].notna()]
    df = df.reset_index(drop=True)

    hours = list(df["hour_start"])
    dev_pos, test_pos = holdout_by_time(hours, test_start)
    y = df[target].to_numpy(dtype=float)
    cols = {
        "A1_plus_permitted": b1_cols + list(_EVENT_COLS),
        "A_news_importance_weighted": b1_cols + list(_EVENT_COLS) + list(_WT_COLS),
    }
    preds = {a: _fit_eval(df[cc].to_numpy(dtype=float)[dev_pos], y[dev_pos],
                          df[cc].to_numpy(dtype=float)[test_pos], 0) for a, cc in cols.items()}
    y_test = y[test_pos]
    blocks = [h.date().toordinal() for h in np.array(hours, dtype=object)[test_pos]]
    active = df.loc[test_pos, "news_salience"].to_numpy() > 0

    arms = {a: {"wape": round(float(wape(y_test, p)), 4), "mae": round(float(mae(y_test, p)), 3)}
            for a, p in preds.items()}
    lfv = llm_feature_value(y_test, preds["A1_plus_permitted"],
                            preds["A_news_importance_weighted"], active, blocks)

    examples = sorted(examples, key=lambda e: -e["news_salience"])[:8]
    return {
        "run_id": f"run_v2-03impwt_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/llm_value/importance_weight_contribution.json",
        "mode": "historical_replay", "claim_status": "measured", "freshness": datetime.now(UTC).isoformat(),
        "grain": "borough-hour", "target": target, "test_from": test_from,
        "n_train_rows": int(len(dev_pos)), "n_test_rows": int(len(test_pos)),
        "feature_form": {
            "news_salience": "news importance in the borough-hour (severity x half-life decay, "
                             "availability-gated); 0 where no news",
            "ev_active_newswt": "ev_active * (1 + news_salience)  -- permit activity amplified if newsworthy",
            "ev_crowd_newswt": "ev_crowd * (1 + news_salience)",
            "invariant": "no news => salience 0 => weight x1.0 => permit feature UNCHANGED (dense base intact)",
        },
        "example_feature_values": examples,
        "test_rows_news_active": int(active.sum()),
        "arms": arms,
        "importance_weight_value_vs_A1": lfv,
        "note": "News reweights the dense permit feed instead of standing alone; can only modulate "
                "permit borough-hours that co-occur with news, never corrupt the base signal.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ml.forecasting.llm_importance_weight_value")
    ap.add_argument("--data-dir", default="data/raw/nyc")
    ap.add_argument("--events", default="data/fixtures/nyc_permitted_events_filtered.jsonl.gz")
    ap.add_argument("--news", default="data/fixtures/news_live/news_gdelt_nyc_2026h1.jsonl")
    ap.add_argument("--perm-events", default="data/fixtures/news_live/claude_events_permitized_2026h1.jsonl")
    ap.add_argument("--test-from", default="2026-05-01")
    ns = ap.parse_args(argv)
    res = run(ns.data_dir, ns.events, ns.news, ns.perm_events, ns.test_from)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "importance_weight_contribution.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    print(f"train={res['n_train_rows']} test={res['n_test_rows']} news_active={res['test_rows_news_active']}")
    print("\nEXAMPLE feature values (what enters the model) — permit x news importance:")
    print(f"  {'borough-hour':26s} {'ev_active':>9s} {'news_sal':>9s} {'ev_active_newswt':>16s}")
    for e in res["example_feature_values"]:
        print(f"  {e['borough']+' '+e['hour']:26s} {e['ev_active']:>9.0f} {e['news_salience']:>9.3f} {e['ev_active_newswt']:>16.3f}")
    for a, s in res["arms"].items():
        print(f"  {a:28s} WAPE={s['wape']:.4f}")
    lfv = res["importance_weight_value_vs_A1"]
    print(f"IMPORTANCE-WEIGHT value vs A1: {lfv['decision']}  skill={lfv['llm_active_skill_pct']}%  "
          f"CI={lfv['active_error_gain_ci95']} (n={lfv['n_llm_active_rows']})")
    print(f"report -> {OUT_DIR}/importance_weight_contribution.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""V2-03 (improved) — measure the IMPROVED LLM event feature and the GRAPH contribution on real
NYC demand, with the LLM Feature Value metric per increment.

Arms (identical cutoffs/splits, same leakage-safe holdout as llm_value_borough):

```
A0            demand + calendar
A1            A0 + structured permitted-event feed
A2_direct     A1 + IMPROVED LLM-news features (time-anchored, type-scoped)   ← no graph
A3_graph      A2_direct + graph neighbor-spillover feature                   ← with graph
```

Two questions, each answered by the LLM Feature Value metric (relative WAPE reduction on the active
subset + block-bootstrap CI):

- **A2_direct − A1**: does the *improved* LLM feature help (vs the old flat-box that hurt −5.52%)?
- **A3_graph − A2_direct**: does the **graph propagation** add value? The label is real demand
  (independent of the graph), so this is a fair "graph vs no-graph" test, not the circular
  retrieval task from V2-06.

Writes `reports/v2/llm_value/graph_contribution.json`.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from config.forecasting import PRIMARY_TARGET
from ml.forecasting.borough_event_lift import _EVENT_COLS, _fit_eval, build_event_index, stream_borough_cells
from ml.forecasting.event_features_v2 import (
    DIRECT_COLS,
    GRAPH_COLS,
    EventFeatureCfg,
    build_direct_index,
    build_graph_index,
)
from ml.forecasting.llm_feature_value import llm_feature_value
from ml.forecasting.metrics import mae, wape
from ml.forecasting.splits import holdout_by_time
from pipelines.collectors import NewsFixtureCollector
from pipelines.features.lags import build_demand_features

_NY = __import__("zoneinfo").ZoneInfo("America/New_York")
OUT_DIR = Path("reports/v2/llm_value")


def _load_events(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def run(data_dir: str, events_path: str, news_path: str, claude_events: str, test_from: str,
        target: str = PRIMARY_TARGET) -> dict:
    test_start = datetime.fromisoformat(test_from).replace(tzinfo=_NY)
    paths = sorted(Path(data_dir).glob("*.zip"))
    if not paths:
        raise SystemExit(f"no trip zips in {data_dir}")
    rows = build_demand_features(stream_borough_cells(paths))
    if not rows:
        raise SystemExit("no feature rows")

    permitted = build_event_index(Path(events_path))
    articles = {a.article_id: a for a in NewsFixtureCollector(Path(news_path)).collect().records}
    events = _load_events(Path(claude_events))
    cfg = EventFeatureCfg()
    direct_idx, direct_diag = build_direct_index(events, articles, cfg)
    graph_idx = build_graph_index(events, articles, cfg)

    b1_cols = sorted({k for r in rows for k in r.features})
    recs: list[dict] = []
    for r in rows:
        rec: dict = {"borough": r.zone_id, "hour_start": r.hour_start, target: r.targets[target]}
        for k in b1_cols:
            rec[k] = r.features.get(k)
        hk = r.hour_start.strftime("%Y-%m-%d %H")
        pe = permitted.get((r.zone_id, hk))
        for c in _EVENT_COLS:
            rec[c] = pe[c] if pe else 0.0
        de = direct_idx.get((r.zone_id, hk))
        for c in DIRECT_COLS:
            rec[c] = de[c] if de else 0.0
        ge = graph_idx.get((r.zone_id, hk))
        for c in GRAPH_COLS:
            rec[c] = ge[c] if ge else 0.0
        recs.append(rec)
    df = pd.DataFrame.from_records(recs).sort_values(["hour_start", "borough"]).reset_index(drop=True)
    for c in ("dep_lag_1", "dep_lag_24", "dep_lag_168", "dep_roll_mean_24"):
        if c in df.columns:
            df = df[df[c].notna()]
    df = df.reset_index(drop=True)

    hours = list(df["hour_start"])
    dev_pos, test_pos = holdout_by_time(hours, test_start)
    if len(dev_pos) == 0 or len(test_pos) == 0:
        raise SystemExit(f"empty split dev={len(dev_pos)} test={len(test_pos)}")

    y = df[target].to_numpy(dtype=float)
    cols = {
        "A0_demand_calendar": b1_cols,
        "A1_plus_permitted": b1_cols + list(_EVENT_COLS),
        "A2_direct_improved": b1_cols + list(_EVENT_COLS) + list(DIRECT_COLS),
        "A3_plus_graph": b1_cols + list(_EVENT_COLS) + list(DIRECT_COLS) + list(GRAPH_COLS),
    }
    preds = {arm: _fit_eval(df[cc].to_numpy(dtype=float)[dev_pos], y[dev_pos],
                            df[cc].to_numpy(dtype=float)[test_pos], 0) for arm, cc in cols.items()}
    y_test = y[test_pos]
    blocks = [h.date().toordinal() for h in np.array(hours, dtype=object)[test_pos]]

    arms = {a: {"wape": round(float(wape(y_test, p)), 4), "mae": round(float(mae(y_test, p)), 3)}
            for a, p in preds.items()}

    direct_active = df.loc[test_pos, list(DIRECT_COLS)].abs().sum(axis=1).to_numpy() > 0
    graph_active = df.loc[test_pos, list(GRAPH_COLS)].abs().sum(axis=1).to_numpy() > 0

    # improved LLM feature value (vs A1) and the GRAPH contribution (vs the improved direct arm)
    improved_vs_a1 = llm_feature_value(y_test, preds["A1_plus_permitted"],
                                       preds["A2_direct_improved"], direct_active, blocks)
    graph_vs_direct = llm_feature_value(y_test, preds["A2_direct_improved"],
                                        preds["A3_plus_graph"], graph_active, blocks)

    return {
        "run_id": f"run_v2-03graph_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/llm_value/graph_contribution.json",
        "mode": "historical_replay",
        "claim_status": "measured",
        "freshness": datetime.now(UTC).isoformat(),
        "grain": "borough-hour (nearest-centroid; approximate)",
        "target": target,
        "test_from": test_from,
        "feature_config": cfg.as_dict(),
        "n_train_rows": int(len(dev_pos)),
        "n_test_rows": int(len(test_pos)),
        "test_rows_direct_active": int(direct_active.sum()),
        "test_rows_graph_active": int(graph_active.sum()),
        "attributed_events": direct_diag["attributed_events"],
        "arms": arms,
        "improved_llm_feature_value_vs_A1": improved_vs_a1,
        "graph_contribution_value_vs_direct": graph_vs_direct,
        "note": (
            "A2_direct = IMPROVED LLM features (event-time anchored, half-life decay, type-scoped "
            "boroughs) — fixes the old flat-24h-from-publish box. A3_graph adds neighbor spillover via "
            "borough-centroid distance decay. graph_contribution_value_vs_direct is the fair graph-vs-"
            "no-graph test on REAL demand (label independent of the graph). MEANINGFUL_POSITIVE there "
            "= the graph measurably improves demand forecasting."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ml.forecasting.llm_graph_value")
    ap.add_argument("--data-dir", default="data/raw/nyc")
    ap.add_argument("--events", default="data/fixtures/nyc_permitted_events_filtered.jsonl.gz")
    ap.add_argument("--news", default="data/fixtures/news_live/news_gdelt_nyc_2026h1.jsonl")
    ap.add_argument("--claude-events", default="data/fixtures/news_live/claude_events_2026h1.jsonl")
    ap.add_argument("--test-from", default="2026-05-01")
    ns = ap.parse_args(argv)

    res = run(ns.data_dir, ns.events, ns.news, ns.claude_events, ns.test_from)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "graph_contribution.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    print(f"train={res['n_train_rows']} test={res['n_test_rows']}  "
          f"direct_active={res['test_rows_direct_active']} graph_active={res['test_rows_graph_active']}")
    for a, s in res["arms"].items():
        print(f"  {a:20s} WAPE={s['wape']:.4f}")
    iv = res["improved_llm_feature_value_vs_A1"]
    gv = res["graph_contribution_value_vs_direct"]
    print(f"IMPROVED LLM feature (vs A1) : {iv['decision']}  skill={iv['llm_active_skill_pct']}%  "
          f"CI95={iv['active_error_gain_ci95']}  (n={iv['n_llm_active_rows']})")
    print(f"GRAPH contribution (vs direct): {gv['decision']}  skill={gv['llm_active_skill_pct']}%  "
          f"CI95={gv['active_error_gain_ci95']}  (n={gv['n_llm_active_rows']})")
    print(f"report -> {OUT_DIR}/graph_contribution.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""V2-03 — can the LLM reconstruct the permit feed FROM news, and does that recover the value that
raw-news extraction loses?

Hypothesis (user): the permitted-events feed works because it is a precise structured DB (a
"graphDB"): exact time + exact borough, known in advance. Raw news doesn't help. So if the LLM
re-extracts news into that SAME permit schema (precise event_start/end + specific borough), the
structured version should help where raw news doesn't.

Arms (identical cutoffs/splits, leakage-safe):

```
A0            demand + calendar
A1            A0 + structured permitted-event feed (the real permit DB)
A2_news_raw   A1 + news features, coarse (type-prior peak hour, type-scoped boroughs)
A2_news_perm  A1 + news features from PERMIT-QUALITY reconstruction (precise event_start/end +
              specific borough, availability-gated)
```

Measured with the LLM Feature Value metric:
- A2_news_perm − A1        : does the permit-quality reconstruction help?
- A2_news_perm − A2_news_raw: does permitizing the STRUCTURE beat raw news?

Honest note: many news items are retrospective reviews (event precedes publication), so the
permitized arm self-excludes them via the availability gate — that timing gap (permits are known in
advance, news is coincident/after) is itself part of the finding, reported via `leakage_dropped`.

Writes `reports/v2/llm_value/permitize_contribution.json`.
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
from ml.forecasting.event_features_v2 import DIRECT_COLS, EventFeatureCfg, build_direct_index, build_permitized_index
from ml.forecasting.llm_feature_value import llm_feature_value
from ml.forecasting.metrics import mae, wape
from ml.forecasting.splits import holdout_by_time
from pipelines.collectors import NewsFixtureCollector
from pipelines.features.lags import build_demand_features

_NY = ZoneInfo("America/New_York")
OUT_DIR = Path("reports/v2/llm_value")
_RAW = tuple(f"raw_{c}" for c in DIRECT_COLS)
_PERM = tuple(f"perm_{c}" for c in DIRECT_COLS)


def _events(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def run(data_dir, events_path, news_path, raw_events, perm_events, test_from, target=PRIMARY_TARGET):
    test_start = datetime.fromisoformat(test_from).replace(tzinfo=_NY)
    paths = sorted(Path(data_dir).glob("*.zip"))
    if not paths:
        raise SystemExit(f"no trip zips in {data_dir}")
    rows = build_demand_features(stream_borough_cells(paths))

    permitted = build_event_index(Path(events_path))
    articles = {a.article_id: a for a in NewsFixtureCollector(Path(news_path)).collect().records}
    cfg = EventFeatureCfg()
    raw_idx, raw_diag = build_direct_index(_events(Path(raw_events)), articles, cfg)
    perm_idx, perm_diag = build_permitized_index(_events(Path(perm_events)), articles, cfg)

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
        re_ = raw_idx.get((r.zone_id, hk))
        for c, rc in zip(DIRECT_COLS, _RAW, strict=True):
            rec[rc] = re_[c] if re_ else 0.0
        pe2 = perm_idx.get((r.zone_id, hk))
        for c, pc in zip(DIRECT_COLS, _PERM, strict=True):
            rec[pc] = pe2[c] if pe2 else 0.0
        recs.append(rec)
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
        "A2_news_raw": b1_cols + list(_EVENT_COLS) + list(_RAW),
        "A2_news_perm": b1_cols + list(_EVENT_COLS) + list(_PERM),
    }
    preds = {a: _fit_eval(df[cc].to_numpy(dtype=float)[dev_pos], y[dev_pos],
                          df[cc].to_numpy(dtype=float)[test_pos], 0) for a, cc in cols.items()}
    y_test = y[test_pos]
    blocks = [h.date().toordinal() for h in np.array(hours, dtype=object)[test_pos]]

    arms = {a: {"wape": round(float(wape(y_test, p)), 4), "mae": round(float(mae(y_test, p)), 3)}
            for a, p in preds.items()}
    raw_active = df.loc[test_pos, list(_RAW)].abs().sum(axis=1).to_numpy() > 0
    perm_active = df.loc[test_pos, list(_PERM)].abs().sum(axis=1).to_numpy() > 0

    perm_vs_a1 = llm_feature_value(y_test, preds["A1_plus_permitted"], preds["A2_news_perm"], perm_active, blocks)
    perm_vs_raw = llm_feature_value(y_test, preds["A2_news_raw"], preds["A2_news_perm"], perm_active, blocks)

    return {
        "run_id": f"run_v2-03permitize_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/llm_value/permitize_contribution.json",
        "mode": "historical_replay", "claim_status": "measured", "freshness": datetime.now(UTC).isoformat(),
        "grain": "borough-hour (nearest-centroid; approximate)", "target": target, "test_from": test_from,
        "n_train_rows": int(len(dev_pos)), "n_test_rows": int(len(test_pos)),
        "raw_news_diag": raw_diag, "permitized_diag": perm_diag,
        "test_rows_raw_active": int(raw_active.sum()), "test_rows_perm_active": int(perm_active.sum()),
        "arms": arms,
        "permitized_value_vs_A1": perm_vs_a1,
        "permitized_value_vs_raw_news": perm_vs_raw,
        "note": (
            "A2_news_perm = LLM reconstruction of news into permit-schema records (precise "
            "event_start/end + specific borough), availability-gated. permitized_diag.leakage_dropped "
            "counts events dropped because the news post-dates the event (retrospective reviews) — the "
            "structural timing gap between advance permits and coincident/after news."
        ),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ml.forecasting.llm_permitize_value")
    ap.add_argument("--data-dir", default="data/raw/nyc")
    ap.add_argument("--events", default="data/fixtures/nyc_permitted_events_filtered.jsonl.gz")
    ap.add_argument("--news", default="data/fixtures/news_live/news_gdelt_nyc_2026h1.jsonl")
    ap.add_argument("--raw-events", default="data/fixtures/news_live/claude_events_2026h1.jsonl")
    ap.add_argument("--perm-events", default="data/fixtures/news_live/claude_events_permitized_2026h1.jsonl")
    ap.add_argument("--test-from", default="2026-05-01")
    ns = ap.parse_args(argv)

    res = run(ns.data_dir, ns.events, ns.news, ns.raw_events, ns.perm_events, ns.test_from)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "permitize_contribution.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    print(f"train={res['n_train_rows']} test={res['n_test_rows']}  "
          f"raw_active={res['test_rows_raw_active']} perm_active={res['test_rows_perm_active']} "
          f"(leakage_dropped={res['permitized_diag']['leakage_dropped']})")
    for a, s in res["arms"].items():
        print(f"  {a:20s} WAPE={s['wape']:.4f}")
    pa, pr = res["permitized_value_vs_A1"], res["permitized_value_vs_raw_news"]
    print(f"permitized vs A1      : {pa['decision']}  skill={pa['llm_active_skill_pct']}%  CI={pa['active_error_gain_ci95']} (n={pa['n_llm_active_rows']})")
    print(f"permitized vs raw-news: {pr['decision']}  skill={pr['llm_active_skill_pct']}%  CI={pr['active_error_gain_ci95']}")
    print(f"report -> {OUT_DIR}/permitize_contribution.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

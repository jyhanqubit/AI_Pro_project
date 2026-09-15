"""V2-03 — IS it sparsity? A permit-event density learning curve.

The claim "LLM-news adds no value because ~19 events is too few" is untested: news differs from the
permit feed on three axes at once — density, precision (exact time/location), and forward-looking
timing. This isolates DENSITY: take the dense permit events that DO help (+2.69% at nowcast) and
subsample them to news-scale counts, holding precision + forward timing at permit quality. Measure
the permit layer's value (A1−A0) as a function of the number of events N.

- If permit value only appears at large N (≫ 100) → density IS the bottleneck; ~19 news events are
  hopeless regardless of quality, and "collect more events" is the real fix.
- If permit value survives at small N (~20–50) → density is NOT the bottleneck; 19 high-quality
  events would suffice, so the news null is about QUALITY (coarse/retrospective/irrelevant), which
  more news would not fix — the cause is elsewhere.

Writes `reports/v2/llm_value/density_curve.json`.
"""

from __future__ import annotations

import argparse
import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from config.forecasting import PRIMARY_TARGET
from ml.forecasting.borough_event_lift import _EVENT_COLS, _fit_eval, build_event_index, stream_borough_cells
from ml.forecasting.llm_feature_value import llm_feature_value
from ml.forecasting.metrics import wape
from ml.forecasting.splits import holdout_by_time
from pipelines.features.lags import build_demand_features

_NY = ZoneInfo("America/New_York")
OUT_DIR = Path("reports/v2/llm_value")
SCRATCH = Path("/tmp/claude-0/-home-user-AI-Pro-project/13a719e5-acff-5289-a79f-baead6ecad81/scratchpad")
GRID = (20, 50, 100, 300, 1000, 3000, 10000, None)  # None = all events


def _permit_lines(path: Path) -> list[str]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return [ln for ln in f if ln.strip()]


def _index_from_sample(lines: list[str], n: int | None, seed: int) -> tuple[dict, int, Path]:
    if n is None or n >= len(lines):
        sample = lines
    else:
        rng = np.random.RandomState(seed)
        sample = [lines[i] for i in sorted(rng.choice(len(lines), size=n, replace=False))]
    tmp = SCRATCH / f"permit_sample_{n}.jsonl"
    tmp.write_text("".join(sample), encoding="utf-8")
    idx = build_event_index(tmp)               # exact same indexer as the real pipeline
    return idx, len(sample), tmp


def run(data_dir, events_path, test_from, target=PRIMARY_TARGET):
    test_start = datetime.fromisoformat(test_from).replace(tzinfo=_NY)
    paths = sorted(Path(data_dir).glob("*.zip"))
    if not paths:
        raise SystemExit(f"no trip zips in {data_dir}")
    rows = build_demand_features(stream_borough_cells(paths))
    b1_cols = sorted({k for r in rows for k in r.features})
    lines = _permit_lines(Path(events_path))
    SCRATCH.mkdir(parents=True, exist_ok=True)

    # base frame once (demand only); permit columns rebuilt per subsample
    base_recs = []
    for r in rows:
        rec = {"borough": r.zone_id, "hour_start": r.hour_start, target: r.targets[target]}
        for k in b1_cols:
            rec[k] = r.features.get(k)
        base_recs.append(rec)
    base_df = pd.DataFrame.from_records(base_recs)

    curve = []
    for n in GRID:
        idx, n_used, _ = _index_from_sample(lines, n, seed=0)
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
        curve.append({
            "n_events_sampled": n_used if n is not None else len(lines),
            "n_events_requested": n,
            "test_active_borough_hours": int(active.sum()),
            "wape_A0": round(float(wape(y_test, p0)), 4),
            "wape_A1": round(float(wape(y_test, p1)), 4),
            "permit_value_decision": lfv["decision"],
            "permit_skill_pct": lfv["llm_active_skill_pct"],
            "permit_ci95": lfv["active_error_gain_ci95"],
        })

    return {
        "run_id": f"run_v2-03density_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/llm_value/density_curve.json",
        "mode": "historical_replay", "claim_status": "measured", "freshness": datetime.now(UTC).isoformat(),
        "grain": "borough-hour", "target": target, "test_from": test_from,
        "controls": "precision + forward-looking timing held at PERMIT quality; only event COUNT varies",
        "curve": curve,
        "note": "If MEANINGFUL_POSITIVE only appears at large N, density is the bottleneck (news's ~19 "
                "events are hopeless). If it appears at small N, density is NOT the cause and the news "
                "null is about quality (coarse/retrospective), which more news data would not fix.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ml.forecasting.llm_density_curve")
    ap.add_argument("--data-dir", default="data/raw/nyc")
    ap.add_argument("--events", default="data/fixtures/nyc_permitted_events_filtered.jsonl.gz")
    ap.add_argument("--test-from", default="2026-05-01")
    ns = ap.parse_args(argv)
    res = run(ns.data_dir, ns.events, ns.test_from)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "density_curve.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    print("PERMIT DENSITY LEARNING CURVE (precision + timing held constant; only count varies)")
    print(f"  {'N_events':>9s} {'active_bh':>9s} {'WAPE_A0':>8s} {'WAPE_A1':>8s}  {'permit A1-A0':>18s}")
    for c in res["curve"]:
        print(f"  {c['n_events_sampled']:>9d} {c['test_active_borough_hours']:>9d} {c['wape_A0']:>8.4f} "
              f"{c['wape_A1']:>8.4f}  {c['permit_value_decision'][:16]:>16s} {str(c['permit_skill_pct'])+'%':>10s}")
    print(f"report -> {OUT_DIR}/density_curve.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

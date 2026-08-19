"""Rolling-origin repetition of the A0/A1/A2 event-feature ablation (V2-03 robustness).

``llm_value_borough`` answers "do event features help?" on **one** train/test split, with a
day-block bootstrap CI over the test period. That CI is conditional on a single fit: it measures
sampling variability of the *evaluation window*, not variability of the *training*. A reviewer can
fairly ask whether the verdict survives a different origin.

This module repeats the same three-arm ablation across several bounded monthly windows, refitting
every arm on each window's expanding training span (section 11.3):

    W_k: test = [month_k, month_k+1)   train = every hour strictly before month_k

and reports, per window, the paired A1-A0 and A2-A1 bootstrap CIs plus a **sign-consistency**
summary over windows. A verdict repeated across origins is far stronger than one lucky split; a
verdict that flips is reported as unstable rather than quietly dropped (section 22).

The panel (trips -> borough-hour cells -> features -> event/news joins) is built once and reused
for every window, so the extra cost over a single run is only the refits.

    python -m ml.forecasting.llm_value_rolling --windows 3
    make v2-llm-value-rolling

Output: ``reports/v2/llm_value/rolling_origin_ablation.json``.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from config.forecasting import PRIMARY_TARGET, REQUIRED_FEATURES
from ml.forecasting.borough_event_lift import (
    _EVENT_COLS,
    _fit_eval,
    build_event_index,
    stream_borough_cells,
)
from ml.forecasting.llm_feature_value import MIN_ACTIVE
from ml.forecasting.llm_value_borough import (
    _NEWS_COLS,
    build_news_llm_index,
    build_news_llm_index_precomputed,
)
from ml.forecasting.metrics import mae, wape
from ml.forecasting.predictive_lift import run_predictive_lift
from pipelines.features.lags import build_demand_features

_NY = ZoneInfo("America/New_York")
OUT_PATH = Path("reports/v2/llm_value/rolling_origin_ablation.json")

ARMS: dict[str, tuple[str, ...]] = {
    "A0_demand_calendar": (),
    "A1_plus_permitted": _EVENT_COLS,
    "A2_plus_llm_news": _EVENT_COLS + _NEWS_COLS,
}


def build_panel(
    data_dir: str,
    events_path: str,
    news_path: str,
    *,
    target: str = PRIMARY_TARGET,
    provider: str = "mock",
    claude_events: str | None = None,
) -> tuple[pd.DataFrame, list[str], dict[str, Any]]:
    """Borough-hour panel with demand/calendar features plus permitted-event and news columns."""
    paths = sorted(Path(data_dir).glob("*.zip"))
    if not paths:
        raise SystemExit(f"no trip zips in {data_dir}")
    rows = build_demand_features(stream_borough_cells(paths))
    if not rows:
        raise SystemExit("no feature rows")

    permitted = build_event_index(Path(events_path))
    if claude_events:
        news_idx, news_diag = build_news_llm_index_precomputed(Path(news_path), Path(claude_events))
    else:
        news_idx, news_diag = build_news_llm_index(Path(news_path), provider=provider)

    b1_cols = sorted({k for r in rows for k in r.features})
    recs: list[dict[str, Any]] = []
    for r in rows:
        rec: dict[str, Any] = {
            "borough": r.zone_id,
            "hour_start": r.hour_start,
            target: r.targets[target],
        }
        for k in b1_cols:
            rec[k] = r.features.get(k)
        hk = r.hour_start.strftime("%Y-%m-%d %H")
        pe = permitted.get((r.zone_id, hk))
        for c in _EVENT_COLS:
            rec[c] = pe[c] if pe else 0.0
        ne = news_idx.get((r.zone_id, hk))
        for c in _NEWS_COLS:
            rec[c] = ne[c] if ne else 0.0
        recs.append(rec)

    df = pd.DataFrame.from_records(recs).sort_values(["hour_start", "borough"])
    df = df.reset_index(drop=True)
    for c in REQUIRED_FEATURES:
        if c in df.columns:
            df = df[df[c].notna()]
    return df.reset_index(drop=True), b1_cols, news_diag


def monthly_windows(hours: pd.Series, n_windows: int) -> list[tuple[datetime, datetime]]:
    """The last ``n_windows`` whole calendar months in the panel, as [start, end) local bounds.

    The earliest month is never a window: it has no strictly-prior training span.
    """
    months = sorted({(h.year, h.month) for h in hours})
    out: list[tuple[datetime, datetime]] = []
    for y, m in months[1:]:
        start = datetime(y, m, 1, tzinfo=_NY)
        end = datetime(y + (m == 12), 1 if m == 12 else m + 1, 1, tzinfo=_NY)
        out.append((start, end))
    return out[-n_windows:]


def evaluate_window(
    df: pd.DataFrame, b1_cols: list[str], start: datetime, end: datetime, target: str
) -> dict[str, Any] | None:
    """Refit every arm on hours < start and score them on [start, end)."""
    hours = df["hour_start"].to_numpy()
    test_mask = (hours >= start) & (hours < end)
    dev_mask = hours < start
    if not test_mask.any() or not dev_mask.any():
        return None

    y = df[target].to_numpy(dtype=float)
    y_test = y[test_mask]
    blocks = [h.date().toordinal() for h in df.loc[test_mask, "hour_start"]]

    preds: dict[str, np.ndarray] = {}
    for arm, extra in ARMS.items():
        x = df[b1_cols + list(extra)].to_numpy(dtype=float)
        preds[arm] = _fit_eval(x[dev_mask], y[dev_mask], x[test_mask], 0)

    def paired(a: str, b: str, active_rows: int) -> dict[str, Any]:
        # Same coverage gate the rest of V2-03 uses (llm_feature_value.MIN_ACTIVE): a window whose
        # extra features are almost never on cannot separate the arms, so it returns blocked_data
        # instead of a spurious "inconclusive" that would dilute the sign-consistency count.
        return run_predictive_lift(
            np.abs(y_test - preds[a]).tolist(),
            np.abs(y_test - preds[b]).tolist(),
            blocks,
            coverage_ok=active_rows >= MIN_ACTIVE,
        )

    news_rows = int((df.loc[test_mask, list(_NEWS_COLS)].abs().sum(axis=1).to_numpy() > 0).sum())
    perm_rows = int((df.loc[test_mask, list(_EVENT_COLS)].abs().sum(axis=1).to_numpy() > 0).sum())

    return {
        "window": f"{start:%Y-%m-%d}..{end:%Y-%m-%d}",
        "n_train_rows": int(dev_mask.sum()),
        "n_test_rows": int(test_mask.sum()),
        "n_day_blocks": len(set(blocks)),
        "test_rows_with_permitted_event": perm_rows,
        "test_rows_with_llm_news_event": news_rows,
        "arms": {
            a: {"wape": round(float(wape(y_test, p)), 4), "mae": round(float(mae(y_test, p)), 3)}
            for a, p in preds.items()
        },
        "A1_minus_A0": paired("A0_demand_calendar", "A1_plus_permitted", perm_rows),
        "A2_minus_A1": paired("A1_plus_permitted", "A2_plus_llm_news", news_rows),
    }


def summarise(results: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """Sign-consistency of one comparison across windows — the point of the whole exercise.

    Windows the coverage gate blocked carry no evidence either way, so they are counted and named
    but excluded from the stability verdict; a verdict over zero informative windows is
    ``no_informative_window`` rather than a manufactured agreement.
    """
    lifts = [r[key] for r in results]
    blocked = [lift for lift in lifts if lift["verdict"] == "blocked_data"]
    usable = [lift for lift in lifts if lift["verdict"] != "blocked_data"]
    positive = sum(1 for lift in usable if lift["ci_95"][0] > 0)
    negative = sum(1 for lift in usable if lift["ci_95"][1] < 0)
    inconclusive = len(usable) - positive - negative
    if not usable:
        stability = "no_informative_window"
    elif positive and negative:
        stability = "sign_flips"
    elif positive == len(usable):
        stability = "consistently_positive"
    elif negative == len(usable):
        stability = "consistently_negative"
    else:
        stability = "mixed_with_inconclusive"
    return {
        "n_windows": len(lifts),
        "n_informative_windows": len(usable),
        "windows_blocked_low_coverage": len(blocked),
        "windows_ci_above_zero": positive,
        "windows_ci_below_zero": negative,
        "windows_inconclusive": inconclusive,
        "mean_gain_per_window": [lift["mean_gain"] for lift in lifts],
        "stability": stability,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ml.forecasting.llm_value_rolling")
    ap.add_argument("--data-dir", default="data/raw/nyc")
    ap.add_argument("--events", default="data/fixtures/nyc_permitted_events_filtered.jsonl.gz")
    ap.add_argument("--news", default="data/fixtures/news_live/news_gdelt_nyc_2026h1.jsonl")
    ap.add_argument("--claude-events", default="data/fixtures/news_live/claude_events_2026h1.jsonl")
    ap.add_argument("--provider", choices=("mock", "anthropic", "openai"), default="mock")
    ap.add_argument("--windows", type=int, default=3)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ns = ap.parse_args(argv)

    have_claude = bool(ns.claude_events) and Path(ns.claude_events).exists()
    claude_events = ns.claude_events if have_claude else None
    provider = "claude-opus-4-8-insession" if claude_events else ns.provider

    print(f"building panel from {ns.data_dir} ...")
    df, b1_cols, news_diag = build_panel(
        ns.data_dir, ns.events, ns.news, provider=ns.provider, claude_events=claude_events
    )
    print(
        f"panel rows={len(df)} boroughs={df['borough'].nunique()} "
        f"news events={news_diag['events']} attributed={news_diag['attributed_events']}"
    )

    windows = monthly_windows(df["hour_start"], ns.windows)
    if not windows:
        raise SystemExit("no usable windows — need at least two calendar months of trips")
    print("windows:", [f"{s:%Y-%m}" for s, _ in windows])

    results: list[dict[str, Any]] = []
    for start, end in windows:
        res = evaluate_window(df, b1_cols, start, end, PRIMARY_TARGET)
        if res is None:
            print(f"  {start:%Y-%m}  skipped (empty split)")
            continue
        results.append(res)
        a1, a2 = res["A1_minus_A0"], res["A2_minus_A1"]
        print(
            f"  {res['window']}  n_test={res['n_test_rows']:>5} blocks={res['n_day_blocks']:>2}  "
            f"A1-A0 {a1['mean_gain']:+.3f} CI{a1['ci_95']} {a1['verdict']}  |  "
            f"A2-A1 {a2['mean_gain']:+.3f} CI{a2['ci_95']} {a2['verdict']}"
        )
    if not results:
        raise SystemExit("every window was empty")

    s_a1 = summarise(results, "A1_minus_A0")
    s_a2 = summarise(results, "A2_minus_A1")
    stamp = datetime.now(UTC)
    payload = {
        "run_id": f"run_v2-03r_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": str(ns.out),
        "mode": "historical_replay",
        "claim_status": "measured",
        "freshness": stamp.isoformat(),
        "grain": "borough-hour (nearest-centroid; approximate)",
        "target": PRIMARY_TARGET,
        "extraction_provider": provider,
        "data_source": ns.data_dir,
        "design": (
            "Rolling-origin repetition of the A0/A1/A2 ablation: each window refits every arm on "
            "the expanding span strictly before it, then bootstraps the paired gain over day "
            "blocks inside that window. Adds the training-side variability a single split omits."
        ),
        "n_windows": len(results),
        "news_attribution": news_diag,
        "windows": results,
        "stability_A1_minus_A0": s_a1,
        "stability_A2_minus_A1": s_a2,
        "note": (
            "A per-window CI is conditional on that window's fit; the stability block is the "
            "cross-origin claim. Verdicts are reported as measured whichever way they fall."
        ),
    }
    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"\nA1-A0 (structured event feed): {s_a1['stability']} "
        f"({s_a1['windows_ci_above_zero']}/{s_a1['n_windows']} windows CI above zero)"
    )
    print(
        f"A2-A1 (LLM news increment)   : {s_a2['stability']} "
        f"({s_a2['windows_ci_below_zero']}/{s_a2['n_windows']} windows CI below zero)"
    )
    print(f"report -> {ns.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

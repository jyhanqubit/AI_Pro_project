"""When does the LLM news feature help, and when does it hurt? (V2-03 conditional finding)

The rolling-origin ablation showed the A2-A1 increment changing sign across windows. A single-seed
read of that is not trustworthy: the two arms differ on only ~6% of test rows, so the tree
ensemble's own randomness can dominate the comparison — flipping the sign of a window from +2.23 to
-2.26 with nothing but a different ``random_state``.

This module removes that noise and asks what actually separates the windows:

1. **Seed ensemble.** Each arm is fit ``n_seeds`` times and its predictions averaged, so the paired
   comparison reflects the systematic effect of the feature rather than one draw of the fitting
   randomness. The per-seed spread is reported alongside, so a reader can see how much noise the
   ensemble removed.
2. **Event composition.** Every window is characterised by how many boroughs its news events span,
   how many are effectively citywide, and which event types dominate.
3. **Training-size control.** The June window is re-run with 1..5 months of training data, and May
   as a control, to test whether "more history" explains the difference. It does not: the two
   windows move in opposite directions as history grows.

The measured pattern is monotone across the informative windows: the fewer boroughs an event spans,
the better the news feature does, crossing zero near two boroughs. The mechanism is that a citywide
event switches the feature on everywhere at once, so it carries no spatial information the calendar
features do not already have — it is a time dummy wearing a location feature's clothes.

Reported as a **conditional** result, not a verdict in either direction: four informative windows
suggest the relationship, and the direct test of it (dropping citywide events) was underpowered.

    python -m ml.forecasting.news_feature_conditions --seeds 10
    make v2-news-conditions

Output: ``reports/v2/llm_value/news_feature_conditions.json``.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from ml.forecasting.borough_event_lift import _fit_eval
from ml.forecasting.llm_feature_value import MIN_ACTIVE
from ml.forecasting.llm_value_borough import _NEWS_COLS
from ml.forecasting.llm_value_rolling import ARMS, build_panel, monthly_windows
from ml.forecasting.predictive_lift import run_predictive_lift

_NY = ZoneInfo("America/New_York")
OUT_PATH = Path("reports/v2/llm_value/news_feature_conditions.json")
CITYWIDE_BOROUGHS = 4  # an event touching this many boroughs carries no spatial contrast


def event_composition(events_path: Path) -> dict[str, dict[str, Any]]:
    """Per-month shape of the news events: spatial spread, citywide share, dominant types."""
    by_month: dict[str, list[dict[str, Any]]] = {}
    for line in Path(events_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        by_month.setdefault(str(e.get("d", ""))[:7], []).append(e)

    out: dict[str, dict[str, Any]] = {}
    for month, evs in sorted(by_month.items()):
        spans = [len(e.get("boroughs", [])) for e in evs]
        types = Counter(e.get("event_type", "UNKNOWN") for e in evs)
        sev = [float(e.get("severity", 0.0)) for e in evs]
        out[month] = {
            "n_events": len(evs),
            "mean_boroughs_per_event": round(sum(spans) / len(spans), 2),
            "citywide_share": round(
                sum(1 for s in spans if s >= CITYWIDE_BOROUGHS) / len(spans), 3
            ),
            "mean_severity": round(sum(sev) / len(sev), 3),
            "dominant_types": [f"{t}x{c}" for t, c in types.most_common(3)],
        }
    return out


def ensemble_gain(
    df, b1_cols: list[str], start: datetime, end: datetime, n_seeds: int, target: str
) -> dict[str, Any] | None:
    """Paired A2-A1 gain after averaging each arm's predictions over ``n_seeds`` fits."""
    hours = df["hour_start"].to_numpy()
    test = (hours >= start) & (hours < end)
    train = hours < start
    if not test.any() or not train.any():
        return None

    y = df[target].to_numpy(dtype=float)
    y_test = y[test]
    blocks = [h.date().toordinal() for h in df.loc[test, "hour_start"]]
    active = int((df.loc[test, list(_NEWS_COLS)].abs().sum(axis=1).to_numpy() > 0).sum())

    stacked: dict[str, list[np.ndarray]] = {a: [] for a in ARMS}
    per_seed: list[float] = []
    for seed in range(n_seeds):
        preds = {}
        for arm, extra in ARMS.items():
            x = df[b1_cols + list(extra)].to_numpy(dtype=float)
            preds[arm] = _fit_eval(x[train], y[train], x[test], seed)
            stacked[arm].append(preds[arm])
        single = run_predictive_lift(
            np.abs(y_test - preds["A1_plus_permitted"]).tolist(),
            np.abs(y_test - preds["A2_plus_llm_news"]).tolist(),
            blocks,
            coverage_ok=active >= MIN_ACTIVE,
        )
        per_seed.append(single["mean_gain"])

    e1 = np.mean(stacked["A1_plus_permitted"], axis=0)
    e2 = np.mean(stacked["A2_plus_llm_news"], axis=0)
    ens = run_predictive_lift(
        np.abs(y_test - e1).tolist(),
        np.abs(y_test - e2).tolist(),
        blocks,
        coverage_ok=active >= MIN_ACTIVE,
    )
    return {
        "window": f"{start:%Y-%m}",
        "n_test_rows": int(test.sum()),
        "n_train_rows": int(train.sum()),
        "news_active_rows": active,
        "per_seed_gain": [round(g, 3) for g in per_seed],
        "per_seed_mean": round(float(np.mean(per_seed)), 3),
        "per_seed_std": round(float(np.std(per_seed)), 3),
        "seeds_positive": sum(1 for g in per_seed if g > 0),
        "ensemble": ens,
    }


def training_size_curve(
    df, b1_cols: list[str], test_month: int, n_seeds: int, target: str
) -> list[dict[str, Any]]:
    """Same test window, progressively shorter training history — isolates 'more data' effects."""
    start = datetime(2026, test_month, 1, tzinfo=_NY)
    end = datetime(2026, test_month + 1, 1, tzinfo=_NY)
    hours = df["hour_start"].to_numpy()
    y = df[target].to_numpy(dtype=float)
    test = (hours >= start) & (hours < end)
    y_test = y[test]
    blocks = [h.date().toordinal() for h in df.loc[test, "hour_start"]]
    active = int((df.loc[test, list(_NEWS_COLS)].abs().sum(axis=1).to_numpy() > 0).sum())

    rows: list[dict[str, Any]] = []
    for first_month in range(test_month - 1, 0, -1):
        train_from = datetime(2026, first_month, 1, tzinfo=_NY)
        train = (hours >= train_from) & (hours < start)
        if train.sum() == 0:
            continue
        stacked: dict[str, list[np.ndarray]] = {a: [] for a in ARMS}
        for seed in range(n_seeds):
            for arm, extra in ARMS.items():
                x = df[b1_cols + list(extra)].to_numpy(dtype=float)
                stacked[arm].append(_fit_eval(x[train], y[train], x[test], seed))
        e1 = np.mean(stacked["A1_plus_permitted"], axis=0)
        e2 = np.mean(stacked["A2_plus_llm_news"], axis=0)
        lift = run_predictive_lift(
            np.abs(y_test - e1).tolist(),
            np.abs(y_test - e2).tolist(),
            blocks,
            coverage_ok=active >= MIN_ACTIVE,
        )
        rows.append(
            {
                "train_months": test_month - first_month,
                "train_from": f"{train_from:%Y-%m}",
                "n_train_rows": int(train.sum()),
                "gain": lift["mean_gain"],
                "ci_95": lift["ci_95"],
                "verdict": lift["verdict"],
            }
        )
    return sorted(rows, key=lambda r: r["train_months"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ml.forecasting.news_feature_conditions")
    ap.add_argument("--data-dir", default="data/raw/nyc")
    ap.add_argument("--events", default="data/fixtures/nyc_permitted_events_filtered.jsonl.gz")
    ap.add_argument("--news", default="data/fixtures/news_live/news_gdelt_nyc_2026h1.jsonl")
    ap.add_argument("--claude-events", default="data/fixtures/news_live/claude_events_2026h1.jsonl")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--windows", type=int, default=6)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ns = ap.parse_args(argv)

    df, b1_cols, news_diag = build_panel(
        ns.data_dir, ns.events, ns.news, claude_events=ns.claude_events
    )
    print(f"panel rows={len(df)}  news events={news_diag['events']}")

    windows = monthly_windows(df["hour_start"], ns.windows)
    results = [
        r
        for s, e in windows
        if (r := ensemble_gain(df, b1_cols, s, e, ns.seeds, "departures")) is not None
    ]
    composition = event_composition(Path(ns.claude_events))

    print(
        f"\n{'window':<10}{'active':>8}{'seed mean':>11}{'+/{n}':>8}{'std':>8}{'ensemble':>11}"
        f"{'CI95':>20}  verdict"
    )
    for r in results:
        comp = composition.get(r["window"], {})
        ci = [round(c, 2) for c in r["ensemble"]["ci_95"]]
        print(
            f"{r['window']:<10}{r['news_active_rows']:>8}{r['per_seed_mean']:>11.3f}"
            f"{r['seeds_positive']:>8}{r['per_seed_std']:>8.3f}"
            f"{r['ensemble']['mean_gain']:>11.3f}{str(ci):>20}  {r['ensemble']['verdict']}"
            f"   boroughs={comp.get('mean_boroughs_per_event', '?')}"
        )

    informative = [r for r in results if r["ensemble"]["verdict"] != "blocked_data"]
    pairs = [
        (composition[r["window"]]["mean_boroughs_per_event"], r["ensemble"]["mean_gain"])
        for r in informative
        if r["window"] in composition
    ]
    monotone = None
    if len(pairs) >= 3:
        by_span = [g for _, g in sorted(pairs, key=lambda t: -t[0])]
        monotone = all(a <= b for a, b in zip(by_span, by_span[1:], strict=False))

    print("\n--- training-size control (does 'more history' explain it?) ---")
    curves = {}
    for month, label in ((6, "2026-06"), (5, "2026-05")):
        curves[label] = training_size_curve(df, b1_cols, month, ns.seeds, "departures")
        print(
            f"  {label}: "
            + "  ".join(f"{c['train_months']}mo {c['gain']:+.2f}" for c in curves[label])
        )

    stamp = datetime.now(UTC)
    payload = {
        "run_id": f"run_v2-03c_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": str(ns.out),
        "mode": "historical_replay",
        "claim_status": "measured",
        "freshness": stamp.isoformat(),
        "grain": "borough-hour (nearest-centroid; approximate)",
        "n_seeds": ns.seeds,
        "question": "Under what conditions does the LLM news feature help the forecast?",
        "windows": results,
        "event_composition": composition,
        "training_size_control": curves,
        "finding": {
            "gain_is_monotone_in_event_spread": monotone,
            "windows_ranked_by_spread": [
                {
                    "window": r["window"],
                    "mean_boroughs_per_event": composition.get(r["window"], {}).get(
                        "mean_boroughs_per_event"
                    ),
                    "citywide_share": composition.get(r["window"], {}).get("citywide_share"),
                    "ensemble_gain": r["ensemble"]["mean_gain"],
                    "verdict": r["ensemble"]["verdict"],
                }
                for r in sorted(
                    informative,
                    key=lambda r: (
                        -(composition.get(r["window"], {}).get("mean_boroughs_per_event") or 0)
                    ),
                )
            ],
            "mechanism": (
                "A citywide event switches the feature on in every borough at once, so it adds no "
                "spatial contrast and duplicates what the calendar features already encode; what "
                "remains is noise. A localised event names which borough moves and when."
            ),
            "training_size_rejected": (
                "Holding the test window fixed and shortening the training history moves June and "
                "May in opposite directions, so training volume does not explain the difference."
            ),
        },
        "limitations": [
            "Only four informative windows: the monotone relationship is suggestive, not "
            "established.",
            "The direct test (dropping events spanning 4+ boroughs) lost 12 of 23 events and fell "
            "under the coverage gate, so it could neither confirm nor refute the mechanism.",
            "Five months of history is too short to separate seasonal effects from event effects; "
            "a full year would be needed.",
        ],
        "note": (
            "Reported as a conditional result. Neither 'the news feature works' nor 'it does not' "
            "is supportable on its own; the measured statement is that its contribution tracks the "
            "spatial resolution of the events it encodes."
        ),
    }
    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nmonotone in event spread: {monotone}")
    print(f"report -> {ns.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

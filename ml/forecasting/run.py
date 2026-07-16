"""Phase 06 runner: ``python -m ml.forecasting.run [citibike_csv_or_zip]``.

Loads the demand panel, verifies that as-of event features are zero on the evaluation window
(the availability rule, §5.2), runs the GridSearch x algorithm-zoo ablation with rolling-origin
evaluation, then writes the results JSON, the interpretation, and two figures. Backs
``make evaluate``. Offline; defaults to the sample fixture, pass the real zip for the real run.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from config.collectors import NEWS_DEMO_FIXTURE
from config.forecasting import (
    ABLATION_LEVELS,
    CV_SPLITS,
    CV_TEST_HOURS,
    FINAL_TEST_HOURS,
    REQUIRED_FEATURES,
)
from ml.forecasting.dataset import load_real_panel, resolve_trip_sources
from ml.forecasting.experiment import run_experiment, usable_frame
from ml.forecasting.interpret import build_interpretation

REPORTS = Path("reports")
DOCS_IMG = Path("docs/img")


def verify_event_features_zero(
    panel_max_hour: datetime, news_source: Path | None = None
) -> dict[str, Any]:
    """Check event availability at the end of the evaluation window (§5.2).

    Returns a small proof record. With the default demo news the events postdate the data, so
    build_graph_features yields zero snapshots at the last cutoff (``event_features_zero=True``).
    With a real overlapping news backfill (``news_source``) the snapshots are non-zero and the
    ablation carries real B2-B4 features — the record reports that honestly either way.
    """
    from pipelines.collectors import NewsFixtureCollector
    from pipelines.events import build_provider, extract_events
    from pipelines.features import build_graph_features

    src = news_source or NEWS_DEMO_FIXTURE
    articles = NewsFixtureCollector(src).collect().records
    events, _ = extract_events(articles, build_provider("mock"))
    snaps = build_graph_features(events, articles, forecast_cutoff=panel_max_hour)
    earliest = min((e.available_at for e in events if e.available_at), default=None)
    return {
        "news_source": str(src),
        "curated_events": len(events),
        "earliest_event_available_at": earliest.isoformat() if earliest else None,
        "eval_window_last_cutoff": panel_max_hour.isoformat(),
        "graph_snapshots_at_cutoff": len(snaps),
        "event_features_zero": len(snaps) == 0,
    }


def _figures(res: dict[str, Any]) -> list[str]:
    """Write feature-importance and algorithm-comparison figures; return saved paths."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - optional visual extra
        print(f"[figures skipped: {exc}]")
        return []

    DOCS_IMG.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []

    # Feature importance (top 12).
    imps = res["permutation_importance"][:12][::-1]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.barh([im["feature"] for im in imps], [im["mean"] for im in imps], color="#1E6FB8")
    ax.set_xlabel("permutation importance (WAPE degradation)")
    ax.set_title(f"Top features — {res['best_algorithm']} ({res['target']})")
    fig.tight_layout()
    p1 = DOCS_IMG / "phase06_feature_importance.png"
    fig.savefig(p1, dpi=120)
    plt.close(fig)
    saved.append(str(p1))

    # Algorithm WAPE comparison (CV vs test) + B0 reference.
    algos = res["algorithms"]
    order = sorted(algos, key=lambda k: algos[k]["cv_wape"])
    fig, ax = plt.subplots(figsize=(7, 4.5))
    x = range(len(order))
    ax.bar(
        [i - 0.2 for i in x],
        [algos[k]["cv_wape"] for k in order],
        width=0.4,
        label="CV WAPE",
        color="#1E6FB8",
    )
    ax.bar(
        [i + 0.2 for i in x],
        [algos[k]["test"]["wape"] for k in order],
        width=0.4,
        label="test WAPE",
        color="#D97E2B",
    )
    ax.axhline(
        res["B0_seasonal_naive"]["wape"], ls="--", color="#555", label="B0 seasonal naive (test)"
    )
    ax.set_xticks(list(x))
    ax.set_xticklabels(order, rotation=30, ha="right")
    ax.set_ylabel("WAPE (lower is better)")
    ax.set_title("Algorithm comparison")
    ax.legend()
    fig.tight_layout()
    p2 = DOCS_IMG / "phase06_algorithm_comparison.png"
    fig.savefig(p2, dpi=120)
    plt.close(fig)
    saved.append(str(p2))
    return saved


# Minimum usable (post-warm-up) hours to run the rolling-origin ablation: the final holdout plus
# the expanding-window CV folds. Below this there is no honest ablation to report.
MIN_USABLE_HOURS = FINAL_TEST_HOURS + CV_SPLITS * CV_TEST_HOURS


def _blocked_report(source: str | Path | None, usable_rows: int, distinct_hours: int) -> None:
    """Write an honest ``blocked_data`` marker instead of crashing on an insufficient panel.

    The ablation needs a trip backfill deep enough to survive the 7-day lag warm-up and still leave
    the rolling-origin holdout + CV folds. The bundled sample is intentionally tiny, so B0-B4 has no
    window to run on. This is reported plainly (§22) — never a fabricated metric.

    The marker is written to a **separate** file so a data-less run never clobbers a real
    ``phase06_results.json`` produced by an earlier ``make evaluate``; the results path stays
    reserved for measured ablation output only. If no real results exist, downstream consumers
    (the model registry) surface a clean "run ``make evaluate``" message rather than a partial file.
    """
    payload = {
        "status": "blocked_data",
        "reason": (
            "insufficient trip history for the rolling-origin ablation after the 7-day lag warm-up"
        ),
        "source": str(source) if source else "bundled sample fixture",
        "usable_rows_after_warmup": usable_rows,
        "distinct_usable_hours": distinct_hours,
        "min_usable_hours_required": MIN_USABLE_HOURS,
        "required_features": list(REQUIRED_FEATURES),
        "ablation_levels": list(ABLATION_LEVELS),
        "note": (
            "No B0-B4 metrics are produced here — a lift claim requires a real Citi Bike trip "
            "backfill (>= a few weeks) whose window overlaps the news/event availability, plus a "
            "news backfill that passes the V2-01 coverage gate. That path needs outbound network "
            "and is documented in docs/EVALUATION_PROTOCOL.md."
        ),
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    marker = REPORTS / "phase06_blocked.json"
    marker.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        f"blocked_data: usable rows after warm-up = {usable_rows} "
        f"({distinct_hours} distinct hours) < required {MIN_USABLE_HOURS}."
    )
    print(f"No fabricated ablation metrics were written; marker at {marker}.")
    print("The measured results file (reports/phase06_results.json) is left untouched.")
    print("Run the real path on a host with data + network:")
    print("  make evaluate CITIBIKE_ZIP=/path/to/real_tripdata.zip")
    print("  (and backfill overlapping news so the V2-01 coverage gate passes).")


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(prog="ml.forecasting.run")
    ap.add_argument(
        "citibike",
        nargs="*",
        default=None,
        help="one or more Citi Bike trip CSV/ZIP files (combined into one panel)",
    )
    ap.add_argument(
        "--data-dir",
        default=None,
        help="a directory of monthly trip archives to combine into one panel (e.g. six months); "
        "de-duplicates a month present as both .zip and extracted .csv",
    )
    ap.add_argument(
        "--news",
        default=None,
        help="a JSONL news backfill whose availability overlaps the trip window; unlocks the real "
        "B2-B4 event ablation (leakage-safe). Omit for the honest zero-overlap baseline.",
    )
    ap.add_argument(
        "--provider",
        choices=("mock", "anthropic"),
        default="mock",
        help="event-extraction provider for --news (mock = deterministic offline; anthropic = real "
        "Claude extraction, needs the SDK + ANTHROPIC_API_KEY). Only used when --news is given.",
    )
    ap.add_argument(
        "--max-months",
        type=int,
        default=None,
        help="bound the panel to the most recent N calendar months of demand. Use this if a full "
        "multi-month NYC window runs out of memory (MemoryError); real data, shorter window.",
    )
    ns = ap.parse_args(argv)
    # Trip sources: a --data-dir, one-or-more positional files, or None (bundled sample).
    source: str | Path | list[Path] | None
    if ns.data_dir:
        source = Path(ns.data_dir)
    elif ns.citibike:
        source = [Path(p) for p in ns.citibike]
    else:
        source = None
    news_source = Path(ns.news) if ns.news else None

    print("ShockFlow AI - Phase 06 forecasting, tuning & evaluation\n")
    trip_files = resolve_trip_sources(source)
    print(f"trip sources: {len(trip_files)} file(s)")
    for tf in trip_files:
        print(f"  {tf}")
    panel = load_real_panel(
        source, news_source=news_source, provider=ns.provider, max_months=ns.max_months
    )
    df = usable_frame(panel)
    distinct_hours = int(df["hour_start"].nunique()) if not df.empty else 0
    if df.empty or distinct_hours < MIN_USABLE_HOURS:
        _blocked_report(str(source), len(df), distinct_hours)
        return
    max_hour = max(df["hour_start"])
    print(
        f"usable rows={len(df)}  zones={df['zone_id'].nunique()}  last_hour={max_hour.isoformat()}"
    )

    proof = verify_event_features_zero(max_hour, news_source)
    print(
        f"event-feature check: {proof['curated_events']} curated events, earliest available "
        f"{proof['earliest_event_available_at']}; graph snapshots at last cutoff="
        f"{proof['graph_snapshots_at_cutoff']}  -> event features zero: "
        f"{proof['event_features_zero']}"
    )

    res = run_experiment(panel)
    res["event_feature_verification"] = proof

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "phase06_results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    interp = build_interpretation(res)
    (REPORTS / "phase06_interpretation.md").write_text(interp, encoding="utf-8")
    figs = _figures(res)

    print(f"\nbest algorithm: {res['best_algorithm']}  params={res['best_params']}")
    b0, best = res["B0_seasonal_naive"], res["algorithms"][res["best_algorithm"]]["test"]
    print(
        f"B0 seasonal naive  WAPE={b0['wape']:.4f}  MAE={b0['mae']:.3f}  "
        f"OCS={b0.get('ocs', float('nan')):.4f}"
    )
    print(
        f"best model         WAPE={best['wape']:.4f}  MAE={best['mae']:.3f}  "
        f"MASE={best['mase']:.4f}  OCS={best.get('ocs', float('nan')):.4f}  "
        f"bias={best.get('bias', float('nan')):+.3f}"
    )
    print("reports: reports/phase06_results.json, reports/phase06_interpretation.md")
    for f in figs:
        print(f"figure: {f}")
    print("\nDone. Rolling-origin evaluation; metrics are from executed fits only.")


if __name__ == "__main__":
    main()

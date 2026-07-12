"""Phase 06 runner: ``python -m ml.forecasting.run [citibike_csv_or_zip]``.

Loads the demand panel, verifies that as-of event features are zero on the evaluation window
(the availability rule, §5.2), runs the GridSearch x algorithm-zoo ablation with rolling-origin
evaluation, then writes the results JSON, the interpretation, and two figures. Backs
``make evaluate``. Offline; defaults to the sample fixture, pass the real zip for the real run.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from config.collectors import NEWS_DEMO_FIXTURE
from ml.forecasting.dataset import load_real_panel
from ml.forecasting.experiment import run_experiment, usable_frame
from ml.forecasting.interpret import build_interpretation

REPORTS = Path("reports")
DOCS_IMG = Path("docs/img")


def verify_event_features_zero(panel_max_hour: datetime) -> dict[str, Any]:
    """Confirm no curated event is available at the end of the evaluation window (§5.2).

    Returns a small proof record: the events exist but their availability postdates the data,
    so build_graph_features yields zero snapshots at the window's last cutoff.
    """
    from pipelines.collectors import NewsFixtureCollector
    from pipelines.events import build_provider, extract_events
    from pipelines.features import build_graph_features

    articles = NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect().records
    events, _ = extract_events(articles, build_provider("mock"))
    snaps = build_graph_features(events, articles, forecast_cutoff=panel_max_hour)
    earliest = min((e.available_at for e in events if e.available_at), default=None)
    return {
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


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    source = Path(argv[0]) if argv else None

    print("ShockFlow AI - Phase 06 forecasting, tuning & evaluation\n")
    panel = load_real_panel(source)
    df = usable_frame(panel)
    max_hour = max(df["hour_start"])
    print(
        f"usable rows={len(df)}  zones={df['zone_id'].nunique()}  last_hour={max_hour.isoformat()}"
    )

    proof = verify_event_features_zero(max_hour)
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

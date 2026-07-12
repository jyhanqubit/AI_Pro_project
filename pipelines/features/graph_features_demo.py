"""As-of graph feature demo: ``python -m pipelines.features.graph_features_demo``.

Extracts demo events, then builds graph features at two cutoffs to show the leakage boundary:
before an event is available its contribution is absent; after, its zones light up. Backs
``make graph-features-demo``.
"""

from __future__ import annotations

from datetime import datetime

from config.collectors import NEWS_DEMO_FIXTURE
from pipelines.collectors import NewsFixtureCollector
from pipelines.events import build_provider, extract_events
from pipelines.features import build_graph_features

STAMP = datetime.fromisoformat("2026-07-12T00:00:00-04:00")


def _run(events, articles, cutoff_iso: str) -> None:
    cutoff = datetime.fromisoformat(cutoff_iso)
    snaps = build_graph_features(events, articles, forecast_cutoff=cutoff, created_at=STAMP)
    print(f"\ncutoff {cutoff_iso}  ->  {len(snaps)} zone snapshot(s)")
    for s in snaps:
        print(
            f"  zone {s.zone_id}  transit_exp={s.features['transit_disruption_exposure']:.3f}  "
            f"impact={s.features['distance_decayed_impact']:.3f}  "
            f"neighbor={s.features['neighbor_zone_impact']:.3f}  events={s.source_event_ids}"
        )


def main() -> None:
    print("ShockFlow AI - as-of graph features (offline)")
    articles = NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect().records
    events, _ = extract_events(articles, build_provider("mock"))

    _run(events, articles, "2026-07-12T13:59:00-04:00")  # before the 14:00 transit event
    _run(events, articles, "2026-07-12T14:30:00-04:00")  # after it becomes available
    _run(events, articles, "2026-07-12T15:30:00-04:00")  # concert also available

    print("\nDone. Features respect the as-of cutoff (available_at <= cutoff).")


if __name__ == "__main__":
    main()

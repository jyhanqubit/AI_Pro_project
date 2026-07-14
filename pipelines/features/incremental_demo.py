"""V1-02 incremental graph-feature demo (offline).

    python -m pipelines.features.incremental_demo

Shows: build a base snapshot from the events available at 14:30, then let the 15:30 concert event
arrive and refresh ONLY the affected zones — and confirm the incremental result equals a full
rebuild (V1_Prompt §8).
"""

from __future__ import annotations

from datetime import datetime

from config.collectors import NEWS_DEMO_FIXTURE
from pipelines.collectors import NewsFixtureCollector
from pipelines.events import build_provider, extract_events
from pipelines.features import build_graph_features
from pipelines.features.incremental import affected_zones, refresh_incremental

STAMP = datetime.fromisoformat("2026-07-12T00:00:00-04:00")
CUTOFF = datetime.fromisoformat("2026-07-12T15:30:00-04:00")
EARLY = datetime.fromisoformat("2026-07-12T14:30:00-04:00")


def main() -> None:
    articles = NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect().records
    events, _ = extract_events(articles, build_provider("mock"))

    base = [e for e in events if e.available_at is not None and e.available_at <= EARLY]
    new = [e for e in events if e.available_at is not None and EARLY < e.available_at <= CUTOFF]
    base_snaps = build_graph_features(base, articles, forecast_cutoff=CUTOFF, created_at=STAMP)

    aff = affected_zones(new, [s.zone_id for s in base_snaps], forecast_cutoff=CUTOFF)
    incremental = refresh_incremental(
        base_snaps, events, articles, forecast_cutoff=CUTOFF, new_events=new, created_at=STAMP
    )
    full = build_graph_features(events, articles, forecast_cutoff=CUTOFF, created_at=STAMP)

    print(f"base zones: {len(base_snaps)}  new events: {len(new)}  affected zones: {len(aff)}")
    print(f"incremental zones: {len(incremental)}  full-rebuild zones: {len(full)}")

    inc = {s.zone_id: s.features for s in incremental}
    fll = {s.zone_id: s.features for s in full}
    equal = inc.keys() == fll.keys() and all(
        abs(inc[z][k] - fll[z][k]) < 1e-9 for z in inc for k in inc[z]
    )
    print(f"incremental == full rebuild: {equal}")
    print("Only the affected zones were recomputed; the rest kept their snapshots (§8).")


if __name__ == "__main__":
    main()

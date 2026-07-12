"""Demo collection runner: ``python -m pipelines.collectors.demo``.

Runs all three fixture collectors offline and prints a provenance/quality summary.
Backs the ``make collect-demo`` target (CLAUDE.md section 19).
"""

from __future__ import annotations

from config.collectors import (
    CITIBIKE_SAMPLE_FIXTURE,
    GBFS_STATION_STATUS_FIXTURE,
    NEWS_DEMO_FIXTURE,
)

from .base import CollectionMetadata
from .citibike import CitiBikeCollector
from .gbfs import GbfsStationStatusCollector
from .news import NewsFixtureCollector


def _print_summary(meta: CollectionMetadata) -> None:
    print(f"[{meta.collector}] mode={meta.mode} source={meta.source}")
    print(
        f"    rows: total={meta.total_rows} accepted={meta.accepted_rows} "
        f"excluded={meta.excluded_rows}"
    )
    if meta.exclusion_reasons:
        print(f"    exclusions: {meta.exclusion_reasons}")
    if meta.warnings:
        print(f"    warnings: {meta.warnings}")


def main() -> None:
    print("ShockFlow AI - demo fixture collection\n")

    citibike = CitiBikeCollector(CITIBIKE_SAMPLE_FIXTURE).collect()
    _print_summary(citibike.metadata)

    news = NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect()
    _print_summary(news.metadata)
    if news.records:
        first = news.records[0].available_at
        last = news.records[-1].available_at
        print(f"    replay window (available_at): {first} .. {last}")

    gbfs = GbfsStationStatusCollector(GBFS_STATION_STATUS_FIXTURE).collect()
    _print_summary(gbfs.metadata)

    print("\nDone. All collection ran offline from fixtures.")


if __name__ == "__main__":
    main()

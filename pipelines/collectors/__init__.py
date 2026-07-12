"""Data collectors (CLAUDE.md section 7). Fixture-first, offline-safe by default."""

from __future__ import annotations

from .base import CollectionMetadata, CollectionResult, Collector
from .citibike import CitiBikeCollector
from .gbfs import GbfsStationStatusCollector
from .news import NewsFixtureCollector, NewsFixtureError

__all__ = [
    "Collector",
    "CollectionResult",
    "CollectionMetadata",
    "CitiBikeCollector",
    "NewsFixtureCollector",
    "NewsFixtureError",
    "GbfsStationStatusCollector",
]

"""Incremental as-of graph-feature refresh (V1_Prompt §8).

When new events arrive, only the **affected** zones are recomputed; the rest keep their existing
snapshots. A zone is affected by a new event when the event is within ``radius_km`` of the zone
centre (direct features) OR within ``radius_km`` of one of the zone's ``max_hops`` neighbour centres
(the ``neighbor_zone_impact`` term). Unaffected zones provably do not change, so the incremental
result is **identical** to a full rebuild (verified in tests/unit/test_incremental_features.py).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from contracts.article import ArticleRecord
from contracts.enums import ExtractionStatus
from contracts.event import EventExtraction
from contracts.feature import FeatureSnapshot

from .graph_features import GraphFeatureConfig, build_graph_features
from .kernels import haversine_km
from .zones import zone_center, zone_for, zone_neighbors


def _event_locations(events: Iterable[EventExtraction]) -> list[tuple[float, float]]:
    return [
        (loc.lat, loc.lng)
        for e in events
        for loc in e.locations
        if loc.lat is not None and loc.lng is not None
    ]


def _as_of(events: Iterable[EventExtraction], cutoff: datetime | None, cfg: GraphFeatureConfig):
    """Only events observable at the cutoff drive the refresh (mirrors build_graph_features)."""
    if cutoff is None:
        return list(events)
    return [
        e
        for e in events
        if e.status is ExtractionStatus.ACCEPTED
        and e.confidence >= cfg.min_confidence
        and e.available_at is not None
        and e.available_at <= cutoff
    ]


def affected_zones(
    new_events: list[EventExtraction],
    known_zones: Iterable[str],
    config: GraphFeatureConfig | None = None,
    forecast_cutoff: datetime | None = None,
) -> set[str]:
    """Zones whose features can change when the as-of-available ``new_events`` are added.

    A future (post-cutoff) event drives no change and creates no zone (leakage guard §5.2).
    """
    cfg = config or GraphFeatureConfig()
    new_locs = _event_locations(_as_of(new_events, forecast_cutoff, cfg))
    new_zones = {zone_for(la, ln, cfg.resolution) for la, ln in new_locs}

    candidates = set(known_zones) | new_zones
    affected: set[str] = set(new_zones)  # a brand-new zone is always (re)built
    for z in candidates:
        # A new event reaching this zone's centre OR any of its max_hops neighbour centres changes
        # the zone's direct features or its neighbour_zone_impact.
        centres = [zone_center(z)] + [zone_center(nz) for nz in zone_neighbors(z, cfg.max_hops)]
        if any(
            haversine_km(la, ln, clat, clng) <= cfg.radius_km
            for (clat, clng) in centres
            for (la, ln) in new_locs
        ):
            affected.add(z)
    return affected


def refresh_incremental(
    base_snapshots: list[FeatureSnapshot],
    all_events: list[EventExtraction],
    all_articles: list[ArticleRecord],
    *,
    forecast_cutoff: datetime,
    new_events: list[EventExtraction],
    config: GraphFeatureConfig | None = None,
    created_at: datetime | None = None,
) -> list[FeatureSnapshot]:
    """Recompute only affected zones; keep the rest. Equivalent to a full rebuild (§8)."""
    cfg = config or GraphFeatureConfig()
    base_by_zone = {s.zone_id: s for s in base_snapshots}
    affected = affected_zones(new_events, base_by_zone.keys(), cfg, forecast_cutoff=forecast_cutoff)

    recomputed = build_graph_features(
        all_events, all_articles, forecast_cutoff=forecast_cutoff,
        zones=sorted(affected), config=cfg, created_at=created_at,
    )
    result = {z: s for z, s in base_by_zone.items() if z not in affected}
    for s in recomputed:
        result[s.zone_id] = s
    return sorted(result.values(), key=lambda s: s.zone_id)

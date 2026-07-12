"""As-of graph feature builder. CLAUDE.md sections 10 and 5.2.

For a forecast cutoff, builds per-zone numeric ``FeatureSnapshot`` rows from the event graph
using ONLY events available as-of the cutoff (available_at <= cutoff). Same events + same
cutoff + same config -> identical output. Source event ids are preserved for traceability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from config.features import H3_RESOLUTION
from config.graph_features import (
    DEFAULT_HALF_LIFE_H,
    DEFAULT_SOURCE_WEIGHT,
    DISTANCE_DECAY_SCALE_KM,
    EVENT_COUNT_WINDOWS_H,
    FEATURE_VERSION,
    GEO_RADIUS_KM,
    HALF_LIFE_BY_TYPE_H,
    MAX_GRAPH_HOPS,
    MIN_CONFIDENCE,
    NEIGHBOR_HOP_PENALTY,
    SOURCE_WEIGHTS,
)
from contracts.article import ArticleRecord
from contracts.enums import EventType, ExtractionStatus
from contracts.event import EventExtraction
from contracts.feature import FeatureSnapshot

from .kernels import exp_distance_decay, half_life_weight, haversine_km
from .zones import zone_center, zone_for, zone_neighbors


@dataclass
class _Relevant:
    event: EventExtraction
    distance_km: float
    age_hours: float
    time_decay: float
    dist_decay: float
    impact: float


@dataclass
class GraphFeatureConfig:
    resolution: int = H3_RESOLUTION
    radius_km: float = GEO_RADIUS_KM
    decay_scale_km: float = DISTANCE_DECAY_SCALE_KM
    default_half_life_h: float = DEFAULT_HALF_LIFE_H
    half_life_by_type: dict[EventType, float] = field(
        default_factory=lambda: dict(HALF_LIFE_BY_TYPE_H)
    )
    windows_h: tuple[int, ...] = EVENT_COUNT_WINDOWS_H
    max_hops: int = MAX_GRAPH_HOPS
    neighbor_penalty: float = NEIGHBOR_HOP_PENALTY
    min_confidence: float = MIN_CONFIDENCE
    source_weights: dict[str, float] = field(default_factory=lambda: dict(SOURCE_WEIGHTS))
    feature_version: str = FEATURE_VERSION

    def as_config_dict(self) -> dict[str, str]:
        return {
            "resolution": str(self.resolution),
            "radius_km": str(self.radius_km),
            "decay_scale_km": str(self.decay_scale_km),
            "default_half_life_h": str(self.default_half_life_h),
            "max_hops": str(self.max_hops),
            "neighbor_penalty": str(self.neighbor_penalty),
            "min_confidence": str(self.min_confidence),
        }


def _as_of(events: list[EventExtraction], cutoff: datetime, cfg: GraphFeatureConfig):
    """Accepted, confident events observable at the cutoff (section 5.2 leakage rule)."""
    return [
        e
        for e in events
        if e.status is ExtractionStatus.ACCEPTED
        and e.confidence >= cfg.min_confidence
        and e.available_at is not None
        and e.available_at <= cutoff
    ]


def _relevant_to_center(
    events: list[EventExtraction], lat: float, lng: float, cutoff: datetime, cfg: GraphFeatureConfig
) -> list[_Relevant]:
    out: list[_Relevant] = []
    for e in events:
        coords = [
            (loc.lat, loc.lng) for loc in e.locations if loc.lat is not None and loc.lng is not None
        ]
        if not coords:
            continue
        dmin = min(haversine_km(lat, lng, la, ln) for la, ln in coords)
        if dmin > cfg.radius_km:
            continue
        age_h = (cutoff - e.available_at).total_seconds() / 3600.0  # type: ignore[operator]
        hl = cfg.half_life_by_type.get(e.event_type, cfg.default_half_life_h)
        tdecay = half_life_weight(age_h, hl)
        ddecay = exp_distance_decay(dmin, cfg.decay_scale_km)
        out.append(_Relevant(e, dmin, age_h, tdecay, ddecay, e.severity * tdecay * ddecay))
    return out


def _source_weight(event: EventExtraction, articles: dict[str, ArticleRecord], cfg) -> float:
    weights = [
        cfg.source_weights.get(articles[a].source, DEFAULT_SOURCE_WEIGHT)
        for a in event.source_article_ids
        if a in articles
    ]
    return max(weights) if weights else DEFAULT_SOURCE_WEIGHT


def _zone_features(
    zone: str,
    events: list[EventExtraction],
    articles: dict[str, ArticleRecord],
    cutoff: datetime,
    cfg: GraphFeatureConfig,
) -> tuple[dict[str, float], list[str]]:
    zlat, zlng = zone_center(zone)
    rel = _relevant_to_center(events, zlat, zlng, cutoff, cfg)

    feats: dict[str, float] = {}

    # Aggregated impact features.
    feats["distance_decayed_impact"] = sum(r.impact for r in rel)
    feats["transit_disruption_exposure"] = sum(
        r.impact for r in rel if r.event.event_type is EventType.TRANSIT_DISRUPTION
    )
    feats["capacity_shock_exposure"] = sum(
        r.event.severity * r.time_decay * r.dist_decay
        for r in rel
        if r.event.capacity_effect.value != "unknown"
    )
    feats["source_weighted_severity"] = sum(
        r.event.severity * _source_weight(r.event, articles, cfg) * r.time_decay for r in rel
    )

    # Confidence / provenance quality.
    confs = [r.event.confidence for r in rel]
    feats["confidence_mean"] = sum(confs) / len(confs) if confs else 0.0
    feats["confidence_max"] = max(confs) if confs else 0.0
    sources = {articles[a].source for r in rel for a in r.event.source_article_ids if a in articles}
    feats["unique_source_count"] = float(len(sources))
    total_refs = sum(len(r.event.source_article_ids) for r in rel)
    unique_articles = len({a for r in rel for a in r.event.source_article_ids})
    feats["duplicate_article_ratio"] = 1.0 - unique_articles / total_refs if total_refs else 0.0

    # Per-type counts within each window.
    for w in cfg.windows_h:
        for et in EventType:
            key = f"event_count_{w}h_{et.value.lower()}"
            feats[key] = float(sum(1 for r in rel if r.age_hours <= w and r.event.event_type is et))

    # Temporal position relative to event start/end (hours).
    upcoming = [
        (r.event.event_start_at - cutoff).total_seconds() / 3600.0
        for r in rel
        if r.event.event_start_at is not None and r.event.event_start_at > cutoff
    ]
    started = [
        (cutoff - r.event.event_start_at).total_seconds() / 3600.0
        for r in rel
        if r.event.event_start_at is not None and r.event.event_start_at <= cutoff
    ]
    remaining = [
        (r.event.event_end_at - cutoff).total_seconds() / 3600.0
        for r in rel
        if r.event.event_start_at is not None
        and r.event.event_end_at is not None
        and r.event.event_start_at <= cutoff <= r.event.event_end_at
    ]
    feats["time_to_event_start"] = min(upcoming) if upcoming else 0.0
    feats["time_since_event_start"] = min(started) if started else 0.0
    feats["event_remaining_duration"] = max(remaining) if remaining else 0.0

    # Neighbour propagation (graph hops).
    neighbor_impact = 0.0
    for nz in zone_neighbors(zone, cfg.max_hops):
        nlat, nlng = zone_center(nz)
        neighbor_impact += sum(
            r.impact for r in _relevant_to_center(events, nlat, nlng, cutoff, cfg)
        )
    feats["neighbor_zone_impact"] = neighbor_impact * cfg.neighbor_penalty

    source_event_ids = sorted({r.event.event_id for r in rel})
    return feats, source_event_ids


def build_graph_features(
    events: list[EventExtraction],
    articles: list[ArticleRecord],
    *,
    forecast_cutoff: datetime,
    zones: list[str] | None = None,
    config: GraphFeatureConfig | None = None,
    created_at: datetime | None = None,
) -> list[FeatureSnapshot]:
    """Build as-of graph FeatureSnapshots for the given (or event-derived) zones."""
    cfg = config or GraphFeatureConfig()
    articles_by_id = {a.article_id: a for a in articles}
    asof = _as_of(events, forecast_cutoff, cfg)

    if zones is None:
        zones_set: set[str] = set()
        for e in asof:
            for loc in e.locations:
                if loc.lat is not None and loc.lng is not None:
                    zones_set.add(zone_for(loc.lat, loc.lng, cfg.resolution))
        zones = sorted(zones_set)

    stamp = created_at or datetime.now(UTC)
    snapshots: list[FeatureSnapshot] = []
    for zone in zones:
        feats, source_ids = _zone_features(zone, asof, articles_by_id, forecast_cutoff, cfg)
        snapshots.append(
            FeatureSnapshot(
                zone_id=zone,
                forecast_cutoff=forecast_cutoff,
                feature_version=cfg.feature_version,
                source_event_ids=source_ids,
                features=feats,
                created_at=stamp,
            )
        )
    return snapshots

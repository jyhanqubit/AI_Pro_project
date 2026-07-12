"""Replay engine backing the API. CLAUDE.md sections 3, 5.2, 9, 12, 13.

Holds the current operating mode and forecast cutoff, and derives everything else as-of that
cutoff from the offline pipeline: which events are available (availability rule, section 5.2),
their graph features, the demo forecast, and the Article -> Event -> H3Zone -> Feature provenance
trace for explanations. No network, no API key (Demo Mode, section 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from config.api import (
    DEFAULT_CUTOFF,
    DEMO_END,
    DEMO_FORECAST_HORIZON_H,
    DEMO_MODEL_VERSION,
    DEMO_START,
    DEMO_TARGET,
)
from config.collectors import NEWS_DEMO_FIXTURE
from contracts.article import ArticleRecord
from contracts.enums import EffectDirection, ExtractionStatus, OperatingMode
from contracts.event import EventExtraction
from contracts.feature import FeatureSnapshot
from pipelines.events import build_provider, extract_events
from pipelines.features import GraphFeatureConfig, build_graph_features

from .forecaster import baseline_forecast, event_aware_forecast

# Zone-level features that an event contributes to (surfaced in the Why-Changed trace).
_EVENT_FEATURE_KEYS = (
    "distance_decayed_impact",
    "transit_disruption_exposure",
    "capacity_shock_exposure",
    "source_weighted_severity",
    "neighbor_zone_impact",
    "confidence_max",
)


@dataclass
class ZoneForecast:
    zone_id: str
    baseline_forecast: float
    event_aware_forecast: float
    forecast_delta: float
    event_exposure: float


@dataclass
class Driver:
    event: EventExtraction
    contributed_features: dict[str, float]


class ReplayEngine:
    """Stateful replay clock over the curated news fixture (offline)."""

    def __init__(self, mode: OperatingMode = OperatingMode.HISTORICAL_REPLAY) -> None:
        self.mode = mode
        self.cutoff: datetime = DEFAULT_CUTOFF
        self.cfg = GraphFeatureConfig()
        self.articles: list[ArticleRecord] = _load_fixture_articles()
        self.articles_by_id = {a.article_id: a for a in self.articles}
        events, _ = extract_events(self.articles, build_provider("mock"))
        self.all_events: list[EventExtraction] = events
        self.events_by_id = {e.event_id: e for e in events}
        # Demo zones = the zones the events can affect once all are available (stable set).
        end_snaps = build_graph_features(events, self.articles, forecast_cutoff=DEMO_END)
        self.demo_zones: list[str] = sorted({s.zone_id for s in end_snaps})

    # --- state -----------------------------------------------------------------------------
    @property
    def feature_version(self) -> str:
        return self.cfg.feature_version

    @property
    def model_version(self) -> str:
        return DEMO_MODEL_VERSION

    def set_cutoff(self, cutoff: datetime) -> None:
        self.cutoff = cutoff

    def available_events(
        self, cutoff: datetime | None = None, disabled_event_ids: tuple[str, ...] = ()
    ) -> list[EventExtraction]:
        """Accepted events observable as-of the cutoff (section 5.2), minus any disabled ones."""
        c = cutoff or self.cutoff
        disabled = set(disabled_event_ids)
        return [
            e
            for e in self.all_events
            if e.status is ExtractionStatus.ACCEPTED
            and e.available_at is not None
            and e.available_at <= c
            and e.event_id not in disabled
        ]

    def _snapshots(
        self, cutoff: datetime, disabled_event_ids: tuple[str, ...] = ()
    ) -> dict[str, FeatureSnapshot]:
        events = self.available_events(cutoff, disabled_event_ids)
        snaps = build_graph_features(
            events, self.articles, forecast_cutoff=cutoff, zones=self.demo_zones, config=self.cfg
        )
        return {s.zone_id: s for s in snaps}

    def _signed_exposure(self, snap: FeatureSnapshot) -> tuple[float, float]:
        """Return (magnitude, signed) event-exposure for a zone from its snapshot + events."""
        magnitude = float(snap.features.get("distance_decayed_impact", 0.0))
        net = 0.0
        for eid in snap.source_event_ids:
            e = self.events_by_id.get(eid)
            if e is None:
                continue
            if e.demand_effect is EffectDirection.INCREASE:
                net += e.severity
            elif e.demand_effect is EffectDirection.DECREASE:
                net -= e.severity
        sign = 1.0 if net > 0 else (-1.0 if net < 0 else 0.0)
        return magnitude, magnitude * sign

    # --- forecasts -------------------------------------------------------------------------
    def forecasts(
        self, cutoff: datetime | None = None, disabled_event_ids: tuple[str, ...] = ()
    ) -> list[ZoneForecast]:
        c = cutoff or self.cutoff
        snaps = self._snapshots(c, disabled_event_ids)
        out: list[ZoneForecast] = []
        for zone in self.demo_zones:
            base = baseline_forecast(zone, c)
            snap = snaps.get(zone)
            if snap is None:
                out.append(ZoneForecast(zone, base, base, 0.0, 0.0))
                continue
            magnitude, signed = self._signed_exposure(snap)
            ea = event_aware_forecast(base, signed)
            out.append(ZoneForecast(zone, base, ea, round(ea - base, 2), round(magnitude, 4)))
        return out

    def zone_forecast(self, zone_id: str, cutoff: datetime) -> ZoneForecast | None:
        for zf in self.forecasts(cutoff):
            if zf.zone_id == zone_id:
                return zf
        return None

    # --- explanation (Why Changed) ---------------------------------------------------------
    def drivers(self, zone_id: str, cutoff: datetime) -> list[Driver]:
        """Per-event provenance + that event's own feature contribution to the zone.

        Each available event is scored alone against the zone, so the trace attributes concrete
        feature values to a single event (honest per-event attribution, not a zone-level lump).
        An event with no contribution to this zone is omitted.
        """
        out: list[Driver] = []
        for e in self.available_events(cutoff):
            snap = build_graph_features(
                [e], self.articles, forecast_cutoff=cutoff, zones=[zone_id], config=self.cfg
            )[0]
            if not snap.source_event_ids:
                continue  # this event does not reach the zone within the radius
            contributed = {
                k: round(float(snap.features[k]), 4)
                for k in _EVENT_FEATURE_KEYS
                if snap.features.get(k, 0.0)
            }
            out.append(Driver(event=e, contributed_features=contributed))
        return out


def _load_fixture_articles() -> list[ArticleRecord]:
    """Load the curated news fixture articles (lazy import to keep module import light)."""
    from pipelines.collectors import NewsFixtureCollector

    return NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect().records


# --- module singleton (FastAPI dependency) -------------------------------------------------
_engine: ReplayEngine | None = None


def get_engine() -> ReplayEngine:
    global _engine
    if _engine is None:
        _engine = ReplayEngine()
    return _engine


def reset_engine() -> None:
    """Test hook: drop the singleton so state does not leak across tests."""
    global _engine
    _engine = None


# expose demo window for the API state endpoint
DEMO_WINDOW = (DEMO_START, DEMO_END)
DEMO_HORIZON = DEMO_FORECAST_HORIZON_H
DEMO_TARGET_NAME = DEMO_TARGET

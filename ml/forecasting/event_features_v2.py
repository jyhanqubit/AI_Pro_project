"""V2-03 (improved) — event → numeric feature builders, direct vs graph-propagated.

Diagnosis of why the first LLM-news features hurt (see V2_LLM_VALUE_ABLATION.md): they were a flat
24-hour box anchored at the *article publish time*, smeared across *all* boroughs for citywide-cued
items, with unbounded severity. Temporally misaligned + spatially over-broad + noisy ⇒ the tree
overfit them and test error rose.

This module fixes the feature engineering and separates two arms so the **graph contribution** can be
measured against real demand (a fair test — the label is Citi Bike demand, independent of the graph):

- **direct (no graph):** each event is anchored to its **event date + a type-specific peak hour**,
  shaped by a **half-life temporal decay** (peaked, not flat), **gated by availability**
  (`available_at ≤ hour`, leakage-safe), and scoped to **type-appropriate boroughs** (weather /
  transit / system may be citywide; venue / gathering / safety / road use named boroughs only — no
  citywide guessing). Severity uses a bounded max, not an unbounded sum.
- **graph:** on top of the direct arm, each event also propagates to *other* boroughs via the
  borough-centroid graph with exponential distance decay — the spatial spillover a point event
  actually has (a Manhattan venue event draws riders from adjacent boroughs). This is the extra
  `news_llm_neighbor` feature; it is non-zero only for boroughs *near* an event borough.

Pure and deterministic so the logic is unit-testable without the trip pipeline.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ml.forecasting.borough_event_lift import _BOROUGH_CENTROIDS
from pipelines.features.kernels import exp_distance_decay, half_life_weight, haversine_km

_NY = ZoneInfo("America/New_York")

DIRECT_COLS = ("news_llm_active", "news_llm_severity", "news_llm_transit", "news_llm_crowd")
GRAPH_COLS = ("news_llm_neighbor",)

CITYWIDE_TYPES = frozenset({"WEATHER_SHOCK", "TRANSIT_DISRUPTION", "SYSTEM_ALERT"})
CROWD_TYPES = frozenset({"LARGE_VENUE_EVENT", "PUBLIC_GATHERING"})
TRANSIT_TYPES = frozenset({"TRANSIT_DISRUPTION", "ROAD_CLOSURE"})
# Type-specific peak hour (local) the event's demand effect centres on. A documented prior, not a
# fabricated exact time: evening for shows/games, daytime for gatherings/incidents, commute for
# weather/transit/road.
PEAK_HOUR = {
    "LARGE_VENUE_EVENT": 19, "PUBLIC_GATHERING": 14, "SAFETY_INCIDENT": 12,
    "WEATHER_SHOCK": 8, "TRANSIT_DISRUPTION": 8, "ROAD_CLOSURE": 8, "SYSTEM_ALERT": 8, "OTHER": 12,
}


@dataclass(frozen=True)
class EventFeatureCfg:
    half_life_h: float = 6.0       # temporal decay: weight halves every 6h from the peak
    span_h: int = 12               # build features within ±span_h of the peak hour
    decay_scale_km: float = 10.0   # spatial decay scale for graph spillover (borough centroids ~8-15km)
    peak_hour: dict = field(default_factory=lambda: dict(PEAK_HOUR))

    def as_dict(self) -> dict[str, str]:
        return {"half_life_h": str(self.half_life_h), "span_h": str(self.span_h),
                "decay_scale_km": str(self.decay_scale_km)}


def scoped_boroughs(event_type: str, boroughs: list[str]) -> list[str]:
    """Boroughs the event is allowed to touch, given its type. Point events use named boroughs only;
    genuinely broad types may stay citywide. No guessing: a point event with no named borough → []."""
    named = [b for b in boroughs if b in _BOROUGH_CENTROIDS]
    if event_type in CITYWIDE_TYPES:
        return named or list(_BOROUGH_CENTROIDS)
    return named  # point event: named only (may be empty → caller skips)


def _anchor(d: str, event_type: str) -> datetime:
    day = datetime.fromisoformat(d).replace(tzinfo=_NY)
    return day.replace(hour=PEAK_HOUR.get(event_type, 12), minute=0, second=0, microsecond=0)


def _hours(anchor: datetime, avail: datetime, cfg: EventFeatureCfg):
    """Yield (hour_key, weight) for each hour in the peaked, availability-gated window."""
    for off in range(-cfg.span_h, cfg.span_h + 1):
        h = anchor + timedelta(hours=off)
        if h < avail:            # leakage gate: cannot use before the news was public
            continue
        w = half_life_weight(abs(off), cfg.half_life_h)
        yield h.strftime("%Y-%m-%d %H"), w


def build_direct_index(events, articles, cfg: EventFeatureCfg | None = None):
    """{(borough, 'YYYY-MM-DD HH') -> {DIRECT_COLS}} — improved, time-anchored, type-scoped."""
    cfg = cfg or EventFeatureCfg()
    idx: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {c: 0.0 for c in DIRECT_COLS})
    diag = {"events": 0, "attributed_events": 0}
    for e in events:
        diag["events"] += 1
        a = articles.get(e["article_id"])
        etype = e.get("event_type", "")
        bs = scoped_boroughs(etype, e.get("boroughs", []))
        if a is None or not bs or not e.get("d"):
            continue
        diag["attributed_events"] += 1
        avail = (a.available_at or max(a.published_at, a.first_seen_at)).astimezone(_NY)
        anchor = _anchor(e["d"], etype)
        sev = float(e.get("severity", 0.5))
        for b in bs:
            for hk, w in _hours(anchor, avail, cfg):
                cell = idx[(b, hk)]
                cell["news_llm_active"] = max(cell["news_llm_active"], w)
                cell["news_llm_severity"] = max(cell["news_llm_severity"], sev * w)
                if etype in TRANSIT_TYPES:
                    cell["news_llm_transit"] = 1.0
                if etype in CROWD_TYPES:
                    cell["news_llm_crowd"] = 1.0
    return idx, diag


def build_graph_index(events, articles, cfg: EventFeatureCfg | None = None):
    """{(borough, 'YYYY-MM-DD HH') -> {GRAPH_COLS}} — neighbor spillover via centroid distance decay.

    For a borough b NOT hosting the event, add severity · time_decay · exp_distance_decay(nearest
    hosting-borough distance). Captures the real spatial spillover of a point event to nearby boroughs.
    """
    cfg = cfg or EventFeatureCfg()
    idx: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {c: 0.0 for c in GRAPH_COLS})
    for e in events:
        a = articles.get(e["article_id"])
        etype = e.get("event_type", "")
        hosts = scoped_boroughs(etype, e.get("boroughs", []))
        if a is None or not hosts or not e.get("d"):
            continue
        avail = (a.available_at or max(a.published_at, a.first_seen_at)).astimezone(_NY)
        anchor = _anchor(e["d"], etype)
        sev = float(e.get("severity", 0.5))
        for b, (blat, blng) in _BOROUGH_CENTROIDS.items():
            if b in hosts:
                continue  # spillover is to OTHER boroughs; the host is covered by the direct arm
            dmin = min(haversine_km(blat, blng, _BOROUGH_CENTROIDS[h][0], _BOROUGH_CENTROIDS[h][1])
                       for h in hosts)
            gw = exp_distance_decay(dmin, cfg.decay_scale_km)
            for hk, w in _hours(anchor, avail, cfg):
                cell = idx[(b, hk)]
                cell["news_llm_neighbor"] = max(cell["news_llm_neighbor"], sev * w * gw)
    return idx

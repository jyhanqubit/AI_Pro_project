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


def _interval_hours(start: datetime, end: datetime, avail: datetime, cfg: EventFeatureCfg):
    """Yield (hour_key, weight) over [start, end] (weight 1.0) plus a half-life tail after end,
    availability-gated. Used when the event carries a PRECISE start/end (permit-quality)."""
    end = min(end, start + timedelta(hours=48))  # cap a long event
    h = start.replace(minute=0, second=0, microsecond=0)
    last = end.replace(minute=0, second=0, microsecond=0)
    while h <= last:
        if h >= avail:
            yield h.strftime("%Y-%m-%d %H"), 1.0
        h += timedelta(hours=1)
    for off in range(1, cfg.span_h + 1):     # decaying tail after the event ends
        ht = last + timedelta(hours=off)
        if ht >= avail:
            yield ht.strftime("%Y-%m-%d %H"), half_life_weight(off, cfg.half_life_h)


def build_permitized_index(events, articles, cfg: EventFeatureCfg | None = None):
    """{(borough, 'YYYY-MM-DD HH') -> {DIRECT_COLS}} from PERMIT-QUALITY news records.

    Same schema as the direct arm, but anchored to the record's PRECISE ``event_start_at`` /
    ``event_end_at`` (the LLM's reconstruction of the news event as a permit-DB entry) and the
    record's SPECIFIC boroughs — not a type-prior peak hour or citywide smear. Still availability-
    gated, so a retrospective review whose event precedes publication self-excludes (honest leakage).
    """
    cfg = cfg or EventFeatureCfg()
    idx: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {c: 0.0 for c in DIRECT_COLS})
    diag = {"events": 0, "attributed_events": 0, "leakage_dropped": 0}
    for e in events:
        diag["events"] += 1
        a = articles.get(e["article_id"])
        etype = e.get("event_type", "")
        bs = scoped_boroughs(etype, e.get("boroughs", []))
        if a is None or not bs or not e.get("event_start_at"):
            continue
        avail = (a.available_at or max(a.published_at, a.first_seen_at)).astimezone(_NY)
        start = datetime.fromisoformat(e["event_start_at"]).astimezone(_NY)
        end = datetime.fromisoformat(e.get("event_end_at") or e["event_start_at"]).astimezone(_NY)
        sev = float(e.get("severity", 0.5))
        hours = list(_interval_hours(start, end, avail, cfg))
        if not hours:
            diag["leakage_dropped"] += 1   # event entirely before the news was public
            continue
        diag["attributed_events"] += 1
        for b in bs:
            for hk, w in hours:
                cell = idx[(b, hk)]
                cell["news_llm_active"] = max(cell["news_llm_active"], w)
                cell["news_llm_severity"] = max(cell["news_llm_severity"], sev * w)
                if etype in TRANSIT_TYPES:
                    cell["news_llm_transit"] = 1.0
                if etype in CROWD_TYPES:
                    cell["news_llm_crowd"] = 1.0
    return idx, diag


SIGNED_COLS = ("news_demand_signal",)


def build_signed_demand_index(events, articles, cfg: EventFeatureCfg | None = None):
    """{(borough, 'YYYY-MM-DD HH') -> {SIGNED_COLS}} — a SIGNED demand-shift signal from the LLM.

    Unlike the (unsigned) salience/importance features, this uses the LLM's ``demand_effect``
    (in [-1,+1]: blizzard ≈ -0.9 suppression, festival/transit-substitution ≈ +0.5 surge). The
    feature is ``demand_effect * severity * time_decay`` (signed), anchored to the precise event
    interval and availability-gated. The model gets the DIRECTION from the LLM instead of having to
    learn the sign from a handful of events; where signs superpose we sum them (net effect).
    """
    cfg = cfg or EventFeatureCfg()
    idx: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {c: 0.0 for c in SIGNED_COLS})
    diag = {"events": 0, "attributed_events": 0, "leakage_dropped": 0}
    for e in events:
        diag["events"] += 1
        a = articles.get(e["article_id"])
        etype = e.get("event_type", "")
        bs = scoped_boroughs(etype, e.get("boroughs", []))
        if a is None or not bs or not e.get("event_start_at") or "demand_effect" not in e:
            continue
        avail = (a.available_at or max(a.published_at, a.first_seen_at)).astimezone(_NY)
        start = datetime.fromisoformat(e["event_start_at"]).astimezone(_NY)
        end = datetime.fromisoformat(e.get("event_end_at") or e["event_start_at"]).astimezone(_NY)
        sev = float(e.get("severity", 0.5))
        eff = float(e["demand_effect"])   # signed direction/magnitude from the LLM
        hours = list(_interval_hours(start, end, avail, cfg))
        if not hours:
            diag["leakage_dropped"] += 1
            continue
        diag["attributed_events"] += 1
        for b in bs:
            for hk, w in hours:
                idx[(b, hk)]["news_demand_signal"] += eff * sev * w   # signed; superpose overlaps
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

"""V2 rider search + operator statistics. CLAUDE.md sections 3, 12, 13.

A usability-focused V2 increment on top of the offline replay demo:

* ``station_search`` — a rider-facing station search over the curated fixture. Matches
  Korean / English names, districts, and aliases (offline gazetteer), then hydrates each hit
  with the as-of live inventory + availability signal. Search is a lookup convenience only; the
  authoritative inventory always comes from the operational fixture, never from the query text.
* ``operator_statistics`` — real aggregations of the as-of replay state (system inventory,
  availability distribution, shortage load, event mix, demand-delta spread, per-zone breakdown).

Every number is computed from the same offline pipeline the rest of the API uses. Nothing here
fabricates demand, price, or inventory (section 22); the demand delta is the labelled
``demo-heuristic-v1`` forecast delta as-of the cutoff, not a measured Phase 06 model output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import cast

from config.collectors import STATION_GAZETTEER_FIXTURE
from contracts.enums import EffectDirection

from .rebalancing import build_problem
from .replay import ReplayEngine

# Availability levels, aligned with the rider UI (apps/web/lib/format.ts). Single source of the
# surplus thresholds so the redesigned home and the stats page agree.
_PLENTY_SURPLUS = 6
_OK_SURPLUS = 2


@dataclass(frozen=True)
class Place:
    station_id: str
    ko: str
    en: str
    area: str
    aliases: tuple[str, ...]

    def haystack(self) -> str:
        parts = [self.station_id, self.ko, self.en, self.area, *self.aliases]
        return " ".join(parts).lower()


@lru_cache(maxsize=1)
def _gazetteer() -> dict[str, Place]:
    raw = json.loads(STATION_GAZETTEER_FIXTURE.read_text(encoding="utf-8"))
    out: dict[str, Place] = {}
    for s in raw["stations"]:
        out[str(s["station_id"])] = Place(
            station_id=str(s["station_id"]),
            ko=str(s["ko"]),
            en=str(s["en"]),
            area=str(s["area"]),
            aliases=tuple(str(a) for a in s.get("aliases", [])),
        )
    return out


def _place(station_id: str) -> Place:
    return _gazetteer().get(station_id, Place(station_id, station_id, station_id, "", ()))


def availability_level(bikes: int, target: int, shortage: int) -> tuple[str, str]:
    """(level, Korean label) from as-of inventory vs. the event-adjusted target.

    Mirrors the rider UI heuristic: a shortage (bikes below target) is ``low``; otherwise the
    surplus (bikes - target) grades plenty / ok / tight.
    """
    surplus = bikes - target
    if shortage > 0:
        return "low", "곧 부족"
    if surplus >= _PLENTY_SURPLUS:
        return "plenty", "넉넉"
    if surplus >= _OK_SURPLUS:
        return "ok", "여유"
    return "tight", "빠듯"


@dataclass(frozen=True)
class StationView:
    station_id: str
    ko: str
    en: str
    area: str
    zone_id: str
    bikes: int
    capacity: int
    docks_free: int
    target: int
    base_target: int
    shortage: int
    surplus: int
    level: str
    level_label: str
    lat: float
    lng: float
    demand_delta: float  # event-aware forecast delta in this zone (demo heuristic), 0 if none
    baseline_forecast: float
    event_aware_forecast: float


def station_views(engine: ReplayEngine, cutoff: datetime) -> list[StationView]:
    """Every demo station with its as-of inventory, availability, and zone demand delta."""
    problem, base_targets = build_problem(engine, cutoff)
    fc = {zf.zone_id: zf for zf in engine.forecasts(cutoff)}
    views: list[StationView] = []
    for s in problem.stations:
        zone = s.zone_id or ""
        zf = fc.get(zone)
        shortage = max(0, s.target - s.bikes)
        level, label = availability_level(s.bikes, s.target, shortage)
        p = _place(s.station_id)
        views.append(
            StationView(
                station_id=s.station_id,
                ko=p.ko,
                en=p.en,
                area=p.area,
                zone_id=zone,
                bikes=s.bikes,
                capacity=s.capacity,
                docks_free=max(0, s.capacity - s.bikes),
                target=s.target,
                base_target=base_targets.get(s.station_id, s.target),
                shortage=shortage,
                surplus=s.bikes - s.target,
                level=level,
                level_label=label,
                lat=s.lat,
                lng=s.lng,
                demand_delta=round(zf.forecast_delta, 2) if zf else 0.0,
                baseline_forecast=round(zf.baseline_forecast, 2) if zf else 0.0,
                event_aware_forecast=round(zf.event_aware_forecast, 2) if zf else 0.0,
            )
        )
    return views


# Rank by availability so the default (empty-query) list leads with rentable stations.
_LEVEL_RANK = {"plenty": 0, "ok": 1, "tight": 2, "low": 3}


def station_search(engine: ReplayEngine, query: str, cutoff: datetime, *, limit: int = 20) -> dict:
    """Offline station search. Empty query returns all stations ranked by availability.

    Matching is a case-insensitive substring over the station's names / district / aliases; the
    live inventory is always hydrated from the fixture (never inferred from the query).
    """
    q = query.strip().lower()
    views = station_views(engine, cutoff)

    if q:
        gaz = _gazetteer()
        scored: list[tuple[int, StationView]] = []
        for v in views:
            hay = gaz.get(v.station_id, _place(v.station_id)).haystack()
            if q in hay:
                # Prefer matches that start the Korean/English name (a tighter hit).
                exact = 0 if (v.ko.lower().startswith(q) or v.en.lower().startswith(q)) else 1
                scored.append((exact, v))
        scored.sort(key=lambda t: (t[0], _LEVEL_RANK.get(t[1].level, 9), -t[1].surplus))
        hits = [v for _, v in scored][:limit]
    else:
        hits = sorted(views, key=lambda v: (_LEVEL_RANK.get(v.level, 9), -v.surplus))[:limit]

    return {
        "mode": engine.mode,
        "cutoff": engine.cutoff,
        "query": query,
        "count": len(hits),
        "stations": [_view_out(v) for v in hits],
    }


def _view_out(v: StationView) -> dict:
    return {
        "station_id": v.station_id,
        "ko": v.ko,
        "en": v.en,
        "area": v.area,
        "zone_id": v.zone_id,
        "bikes": v.bikes,
        "capacity": v.capacity,
        "docks_free": v.docks_free,
        "target": v.target,
        "base_target": v.base_target,
        "shortage": v.shortage,
        "surplus": v.surplus,
        "level": v.level,
        "level_label": v.level_label,
        "lat": v.lat,
        "lng": v.lng,
        "demand_delta": v.demand_delta,
        "baseline_forecast": v.baseline_forecast,
        "event_aware_forecast": v.event_aware_forecast,
    }


def _round(x: float, n: int = 2) -> float:
    return round(float(x), n)


def operator_statistics(engine: ReplayEngine, cutoff: datetime) -> dict:
    """Real aggregate statistics of the as-of replay state for the operator analytics screen."""
    views = station_views(engine, cutoff)
    events = engine.available_events(cutoff)
    forecasts = engine.forecasts(cutoff)

    total_bikes = sum(v.bikes for v in views)
    total_capacity = sum(v.capacity for v in views)
    total_docks = sum(v.docks_free for v in views)

    avail_counts = {"plenty": 0, "ok": 0, "tight": 0, "low": 0}
    for v in views:
        avail_counts[v.level] = avail_counts.get(v.level, 0) + 1

    stations_in_shortage = sum(1 for v in views if v.shortage > 0)
    total_shortage = sum(v.shortage for v in views)
    total_surplus = sum(max(0, v.surplus) for v in views)

    effect_counts = {"increase": 0, "decrease": 0, "unknown": 0}
    type_counts: dict[str, int] = {}
    for e in events:
        if e.demand_effect is EffectDirection.INCREASE:
            effect_counts["increase"] += 1
        elif e.demand_effect is EffectDirection.DECREASE:
            effect_counts["decrease"] += 1
        else:
            effect_counts["unknown"] += 1
        et = str(e.event_type)
        type_counts[et] = type_counts.get(et, 0) + 1

    deltas = [zf.forecast_delta for zf in forecasts]
    affected = [zf for zf in forecasts if abs(zf.forecast_delta) > 1e-9]
    demand_delta_total = _round(sum(deltas))
    demand_delta_max = _round(max((abs(d) for d in deltas), default=0.0))
    demand_delta_mean_affected = (
        _round(sum(zf.forecast_delta for zf in affected) / len(affected)) if affected else 0.0
    )

    # Per-zone breakdown (one demo station per zone in the fixture; group defensively anyway).
    by_zone: dict[str, list[StationView]] = {}
    for v in views:
        by_zone.setdefault(v.zone_id, []).append(v)
    fc_by_zone = {zf.zone_id: zf for zf in forecasts}
    zones = []
    for zone_id, zvs in by_zone.items():
        zbikes = sum(v.bikes for v in zvs)
        zcap = sum(v.capacity for v in zvs)
        zf = fc_by_zone.get(zone_id)
        worst_level = max(zvs, key=lambda v: _LEVEL_RANK.get(v.level, 9)).level
        head = zvs[0]
        zones.append(
            {
                "zone_id": zone_id,
                "ko": head.ko,
                "en": head.en,
                "area": head.area,
                "station_count": len(zvs),
                "bikes": zbikes,
                "capacity": zcap,
                "utilization": _round(zbikes / zcap) if zcap else 0.0,
                "baseline_forecast": _round(zf.baseline_forecast) if zf else 0.0,
                "event_aware_forecast": _round(zf.event_aware_forecast) if zf else 0.0,
                "forecast_delta": _round(zf.forecast_delta) if zf else 0.0,
                "event_exposure": _round(zf.event_exposure, 4) if zf else 0.0,
                "worst_level": worst_level,
                "shortage": sum(v.shortage for v in zvs),
            }
        )
    zones.sort(key=lambda z: -abs(cast(float, z["forecast_delta"])))
    top_surge = [z for z in zones if cast(float, z["forecast_delta"]) > 1e-9][:3]

    return {
        "mode": engine.mode,
        "cutoff": engine.cutoff,
        "model_version": engine.model_version,
        "feature_version": engine.feature_version,
        "note": (
            "과거 재생(Historical Replay) 상태의 실제 집계입니다. 수요 변화(Δ)는 라벨이 붙은 데모 "
            "heuristic(demo-heuristic-v1) 예보 델타이며, 측정된 Phase 06 모델 출력이 아닙니다. "
            "모든 값은 오프라인 fixture에서 계산됩니다."
        ),
        "station_count": len(views),
        "total_bikes": total_bikes,
        "total_capacity": total_capacity,
        "total_docks_free": total_docks,
        "system_utilization": _round(total_bikes / total_capacity) if total_capacity else 0.0,
        "availability_counts": avail_counts,
        "stations_in_shortage": stations_in_shortage,
        "total_shortage_units": total_shortage,
        "total_surplus_units": total_surplus,
        "available_event_count": len(events),
        "events_by_effect": effect_counts,
        "events_by_type": type_counts,
        "affected_zone_count": len(affected),
        "demand_delta_total": demand_delta_total,
        "demand_delta_max": demand_delta_max,
        "demand_delta_mean_affected": demand_delta_mean_affected,
        "zones": zones,
        "top_surge_zones": top_surge,
    }

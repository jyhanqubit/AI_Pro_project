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

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import cast

from config.api import DEMO_END, DEMO_START
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


def _hourly_cutoffs(step_hours: int = 1) -> list[datetime]:
    """Hourly cutoffs spanning the demo replay window [DEMO_START, DEMO_END] inclusive."""
    out: list[datetime] = []
    c = DEMO_START
    step = timedelta(hours=step_hours)
    while c <= DEMO_END:
        out.append(c)
        c = c + step
    return out


def operator_timeline(engine: ReplayEngine, *, step_hours: int = 1) -> dict:
    """As-of aggregates evaluated at each hour across the replay window (event-window analytics).

    For every hourly cutoff the same offline pipeline is recomputed as-of that boundary, so the
    series honestly shows the event onset: before an event's ``available_at`` it contributes no
    demand delta and no raised-target shortage. Station inventory itself is a static fixture, so
    utilization is flat by design; the shortage / delta / event series are what move.
    """
    points = []
    for c in _hourly_cutoffs(step_hours):
        views = station_views(engine, c)
        forecasts = engine.forecasts(c)
        events = engine.available_events(c)
        affected = [zf for zf in forecasts if abs(zf.forecast_delta) > 1e-9]
        points.append(
            {
                "cutoff": c,
                "event_count": len(events),
                "affected_zone_count": len(affected),
                "total_shortage_units": sum(v.shortage for v in views),
                "stations_in_shortage": sum(1 for v in views if v.shortage > 0),
                "demand_delta_total": _round(sum(zf.forecast_delta for zf in forecasts)),
                "demand_delta_max": _round(
                    max((abs(zf.forecast_delta) for zf in forecasts), default=0.0)
                ),
            }
        )
    # Event onset markers (the first cutoff at which each demand-effect event became available).
    markers = []
    seen: set[str] = set()
    for e in sorted(engine.all_events, key=lambda x: x.available_at or DEMO_END):
        if e.available_at is None or e.available_at < DEMO_START or e.available_at > DEMO_END:
            continue
        if e.event_id in seen:
            continue
        seen.add(e.event_id)
        markers.append(
            {
                "event_id": e.event_id,
                "event_type": str(e.event_type),
                "event_title": e.event_title,
                "available_at": e.available_at,
                "demand_effect": str(e.demand_effect),
            }
        )

    return {
        "mode": engine.mode,
        "model_version": engine.model_version,
        "feature_version": engine.feature_version,
        "window_start": DEMO_START,
        "window_end": DEMO_END,
        "step_hours": step_hours,
        "note": (
            "각 시각(as-of)마다 오프라인 파이프라인을 다시 계산한 실제 시계열입니다. 이벤트 공개 "
            "이전에는 수요 변화(Δ)와 목표 상향에 따른 부족이 발생하지 않습니다. 재고는 정적 "
            "fixture이므로 가동률은 설계상 일정하며, 움직이는 것은 부족·Δ·이벤트 계열입니다."
        ),
        "points": points,
        "event_markers": markers,
    }


def allocate_extra_bikes(engine: ReplayEngine, cutoff: datetime, extra: int) -> dict:
    """Distribute ``extra`` operator-supplied bikes over the as-of network to maximise benefit.

    Reuses the as-of rebalancing problem (event-adjusted targets) and the classical allocation
    optimiser. The result is exact (the objective is separable/convex, so greedy is optimal) and
    honest: bikes with no beneficial placement are reported as held back, not force-placed.
    """
    from optimization.classical.allocation import allocate_extra_bikes as _allocate

    problem, base_targets = build_problem(engine, cutoff)
    result = _allocate(problem, extra)
    gaz = _gazetteer()

    # Show the biggest allocations first, then the untouched stations (sort the typed rows).
    ordered = sorted(
        result.stations,
        key=lambda sa: (-sa.added, -sa.shortage_before, sa.station_id),
    )
    stations = []
    for sa in ordered:
        p = gaz.get(sa.station_id, _place(sa.station_id))
        stations.append(
            {
                "station_id": sa.station_id,
                "ko": p.ko,
                "en": p.en,
                "area": p.area,
                "zone_id": sa.zone_id,
                "bikes_before": sa.bikes_before,
                "added": sa.added,
                "bikes_after": sa.bikes_after,
                "target": sa.target,
                "base_target": base_targets.get(sa.station_id, sa.target),
                "capacity": sa.capacity,
                "shortage_before": sa.shortage_before,
                "shortage_after": sa.shortage_after,
            }
        )

    return {
        "mode": engine.mode,
        "cutoff": engine.cutoff,
        "model_version": engine.model_version,
        "feature_version": engine.feature_version,
        "method": "greedy-marginal-exact",
        "extra_requested": result.extra_requested,
        "placed": result.placed,
        "leftover": result.leftover,
        "shortage_units_before": result.shortage_units_before,
        "shortage_units_after": result.shortage_units_after,
        "overflow_units_before": result.overflow_units_before,
        "overflow_units_after": result.overflow_units_after,
        "cost_before": result.cost_before,
        "cost_after": result.cost_after,
        "benefit": result.benefit,
        "shortage_reduction": result.shortage_units_before - result.shortage_units_after,
        "stations": stations,
        "note": (
            "운영자가 입력한 추가 자전거를 as-of 목표 재고에 맞춰 최적 분배한 결과입니다. 비용은 "
            "비대칭 운영 목적(부족 3 : 과잉 1, config/rebalancing.py)이며, 목적이 분리·볼록이라 "
            "greedy 한계이익 배분이 전역 최적입니다(테스트에서 완전탐색과 일치 검증). 목표를 이미 "
            "충족한 뒤의 자전거는 과잉만 늘리므로 배치하지 않고 창고 보유로 정직하게 보고합니다. "
            "목표는 라벨이 붙은 데모 heuristic(demo-heuristic-v1) 예보 델타로 상향되며, 측정된 "
            "Phase 06 모델이 아닙니다."
        ),
    }


def _alias_index() -> dict[str, tuple[str, ...]]:
    """Per-station lowercased match terms for the copilot slot resolver (from the gazetteer)."""
    out: dict[str, tuple[str, ...]] = {}
    for sid, p in _gazetteer().items():
        out[sid] = tuple(t.lower() for t in (p.ko, p.en, p.area, sid, *p.aliases) if t)
    return out


def _views_by_id(views: list[StationView]) -> dict[str, StationView]:
    return {v.station_id: v for v in views}


def rider_ask(engine: ReplayEngine, query: str, cutoff: datetime) -> dict:
    """Answer a rider's natural-language query, grounded entirely in the as-of tool results.

    The intent is parsed deterministically (``rider_copilot.parse``); the answer text copies live
    numbers from ``station_views`` / available events verbatim — nothing is fabricated. Unsupported
    queries return ``supported=False`` with a clarification instead of a made-up answer.
    """
    from .rider_copilot import parse

    parsed = parse(query, _alias_index())
    views = station_views(engine, cutoff)
    by_id = _views_by_id(views)
    good = sorted(
        (v for v in views if v.level in ("plenty", "ok")),
        key=lambda v: (_LEVEL_RANK[v.level], -v.surplus),
    )
    low = sorted(
        (v for v in views if v.level in ("low", "tight")),
        key=lambda v: (-_LEVEL_RANK[v.level], v.shortage * -1),
    )
    events = engine.available_events(cutoff)

    supported = True
    stations: list[StationView] = []
    answer = ""

    if parsed.intent in ("status_at_location", "return_at_location") and parsed.station_id:
        v = by_id[parsed.station_id]
        stations = [v]
        if parsed.intent == "return_at_location":
            answer = f"{v.ko}은(는) 지금 반납 여유가 {v.docks_free}칸이에요 (정원 {v.capacity}대)."
        else:
            answer = (
                f"{v.ko}은(는) 지금 자전거 {v.bikes}대예요. 상태: {v.level_label}. "
                f"반납 여유는 {v.docks_free}칸입니다."
            )
            if v.demand_delta > 0.001:
                answer += " 이벤트로 이 지역 수요가 늘고 있어요."
            elif v.level in ("low", "tight") and good:
                answer += f" 재고가 빠듯하면 {good[0].ko}({good[0].bikes}대)도 확인해 보세요."

    elif parsed.intent == "best_availability":
        stations = good[:3]
        if stations:
            names = ", ".join(f"{v.ko}({v.bikes}대)" for v in stations)
            answer = f"지금 빌리기 좋은 곳은 {names}예요."
        else:
            answer = "지금은 어느 곳도 넉넉하지 않아요. 곧 부족한 지역을 피해 서두르는 게 좋아요."

    elif parsed.intent == "shortage_warning":
        stations = low[:3]
        if stations:
            names = ", ".join(v.ko for v in stations)
            alt = f" 여유 지역({', '.join(v.ko for v in good[:2])})을 이용하세요." if good else ""
            answer = f"곧 부족할 수 있는 곳: {names}.{alt}"
        else:
            answer = "지금은 부족한 대여소가 없어요. 어디서든 빌리기 좋아요."

    elif parsed.intent == "best_return":
        stations = sorted(views, key=lambda v: -v.docks_free)[:3]
        names = ", ".join(f"{v.ko}({v.docks_free}칸)" for v in stations)
        answer = f"반납 여유가 많은 곳: {names}."

    elif parsed.intent == "events":
        if events:
            lines = "; ".join(f"{i + 1}) {e.event_title}" for i, e in enumerate(events))
            answer = (
                f"지금 영향을 주는 이벤트 {len(events)}건: {lines}. 관련 지역 수요가 늘 수 있어요."
            )
            if parsed.station_id:
                v = by_id[parsed.station_id]
                stations = [v]
        else:
            answer = "현재 시각 기준으로 공개된 이벤트는 없어요. 수요는 평상시 수준입니다."

    elif parsed.intent == "help":
        answer = (
            "대여소 찾기, 빌리기 좋은 곳, 곧 부족한 곳, 반납 여유, 지금 이벤트를 알려드릴 수 "
            "있어요. 예: '시청 근처 자전거 있어?', '반납 어디가 여유로워?', '지금 무슨 일 있어?'"
        )

    else:  # unknown -> clarification, never a fabricated answer
        supported = False
        answer = (
            "질문을 이해하지 못했어요. 대여소 찾기, 빌리기 좋은 곳, 곧 부족한 곳, 반납 여유, "
            "지금 이벤트를 물어봐 주세요. 예: '뉴포트 자전거 있어?'"
        )

    return {
        "mode": engine.mode,
        "cutoff": engine.cutoff,
        "model_version": engine.model_version,
        "query": query,
        "intent": parsed.intent,
        "supported": supported,
        "answer": answer,
        "stations": [_view_out(v) for v in stations],
        "events": [
            {
                "event_id": e.event_id,
                "event_type": str(e.event_type),
                "event_title": e.event_title,
                "demand_effect": str(e.demand_effect),
            }
            for e in (events if parsed.intent == "events" else [])
        ],
        "note": (
            "규칙 기반(비-LLM) 도우미입니다. 모든 수치는 현재 재생 시각(as-of)의 실제 재고에서 "
            "그대로 가져온 값이며 임의로 생성하지 않습니다. 이해하지 못한 질문에는 답을 지어내지 "
            "않고 되물어봅니다."
        ),
    }


def pricing_quotes(
    engine: ReplayEngine,
    cutoff: datetime,
    *,
    stale: bool = False,
    safety: bool = False,
) -> dict:
    """SIMULATED SHADOW fare quotes for every station as-of the cutoff (V2-05).

    Each quote applies the deterministic scarcity kernel with hard guardrails. ``stale`` and
    ``safety`` are explicit what-if scenario toggles (clearly labelled) that demonstrate the
    base-fare fallbacks; the real safety block is also derived from any available SAFETY_INCIDENT
    event. Never applied to a rider (shadow mode); all results are labelled simulated.
    """
    from config.pricing_v2 import (
        NO_SURCHARGE_EVENT_TYPES,
        SIMULATED_DISCLAIMER,
        DynamicFareConfig,
    )
    from ml.pricing.dynamic import price_quote

    cfg = DynamicFareConfig()
    views = station_views(engine, cutoff)
    events = engine.available_events(cutoff)
    # A safety/emergency event anywhere in the system suppresses surcharge (conservative).
    real_safety = any(str(e.event_type) in NO_SURCHARGE_EVENT_TYPES for e in events)
    safety_block = safety or real_safety
    total_surplus = sum(max(0, v.surplus) for v in views)

    quotes = []
    for v in views:
        neighbor_spare = float(total_surplus - max(0, v.surplus))  # spare bikes elsewhere
        q = price_quote(
            bikes=v.bikes,
            target=v.target,
            capacity=v.capacity,
            surplus=v.surplus,
            demand_delta=v.demand_delta,
            neighbor_spare=neighbor_spare,
            stale=stale,
            safety_block=safety_block,
            cfg=cfg,
        )
        digest = hashlib.sha1(
            f"{v.station_id}|{cutoff.isoformat()}|{q.tier_multiplier}|{cfg.version}|"
            f"stale={stale}|safety={safety_block}".encode()
        ).hexdigest()[:10]
        quotes.append(
            {
                "station_id": v.station_id,
                "ko": v.ko,
                "en": v.en,
                "zone_id": v.zone_id,
                "level": v.level,
                "level_label": v.level_label,
                "bikes": v.bikes,
                "target": v.target,
                "capacity": v.capacity,
                "demand_delta": v.demand_delta,
                "scarcity_score": q.scarcity_score,
                "components": {
                    "shortage_probability": round(q.components.shortage_probability, 4),
                    "normalized_gap": round(q.components.normalized_gap, 4),
                    "event_impact": round(q.components.event_impact, 4),
                    "neighbor_buffer": round(q.components.neighbor_buffer, 4),
                },
                "base_fare": q.base_fare,
                "tier_multiplier": q.tier_multiplier,
                "scarcity_surcharge": q.scarcity_surcharge,
                "final_price": q.final_price,
                "balancing_credit": q.balancing_credit,
                "tier_reason": q.tier_reason,
                "guardrails": {
                    "stale": q.stale,
                    "safety_block": q.safety_block,
                    "capped": q.capped,
                },
                "quote_id": digest,
            }
        )
    # Show the most-surcharged first.
    quotes.sort(
        key=lambda x: (
            -cast(float, x["tier_multiplier"]),
            -cast(float, x["scarcity_score"]),
            cast(str, x["station_id"]),
        )
    )

    return {
        "mode": engine.mode,
        "cutoff": engine.cutoff,
        "model_version": engine.model_version,
        "pricing_config_version": cfg.version,
        "is_simulated": True,
        "shadow": True,
        "disclaimer": SIMULATED_DISCLAIMER,
        "scenario": {"stale": stale, "safety": safety_block},
        "base_fare": cfg.base_fare,
        "tiers": list(cfg.tiers),
        "quotes": quotes,
        "note": (
            "SIMULATED SHADOW 요금입니다 — 실제 라이더에게 적용되지 않습니다. 할증은 station "
            "부족(scarcity) pressure로만 결정되며, 라이더 신원·감면요금·보호속성은 입력에 쓰이지 "
            "않습니다. 안전/긴급 이벤트나 stale 데이터에는 할증하지 않고 기본요금으로 되돌립니다. "
            "component 합(base+surcharge)은 최종가와 일치하며, 상한은 1.50배입니다. 탄력성/전환 "
            "추정치가 없으므로 모든 결과는 simulated로 표기합니다."
        ),
    }


def ops_ask(engine: ReplayEngine, query: str, cutoff: datetime) -> dict:
    """Answer an operator's NL query, grounded in the same artifacts the dashboards use (V2-07).

    Every fact is copied from ``operator_statistics`` / ``pricing_quotes`` — the copilot never
    fabricates a number and never runs arbitrary SQL (allowlisted intents only). Where useful it
    returns a deep-link so the UI can jump to the matching screen.
    """
    from .ops_copilot import parse

    parsed = parse(query)
    stats = operator_statistics(engine, cutoff)
    supported = True
    facts: dict[str, object] = {}
    link: dict[str, str] | None = None
    answer = ""

    if parsed.intent == "overview":
        util = round(stats["system_utilization"] * 100)
        answer = (
            f"현재 가동률 {util}% ({stats['total_bikes']}/{stats['total_capacity']}대), "
            f"부족 대여소 {stats['stations_in_shortage']}곳, 반영 이벤트 "
            f"{stats['available_event_count']}건입니다."
        )
        facts = {
            "system_utilization": stats["system_utilization"],
            "total_bikes": stats["total_bikes"],
            "stations_in_shortage": stats["stations_in_shortage"],
            "available_event_count": stats["available_event_count"],
        }
        link = {"label": "운영 통계 열기", "href": "/statistics"}

    elif parsed.intent == "shortage":
        short_zones = [z for z in stats["zones"] if z["shortage"] > 0]
        names = ", ".join(z["ko"] for z in short_zones[:3]) or "없음"
        answer = (
            f"부족 대여소 {stats['stations_in_shortage']}곳, 총 부족 "
            f"{stats['total_shortage_units']}대입니다. 부족 지역: {names}. "
            "재배치 계획에서 보완할 수 있어요."
        )
        facts = {
            "stations_in_shortage": stats["stations_in_shortage"],
            "total_shortage_units": stats["total_shortage_units"],
            "shortage_zones": [z["ko"] for z in short_zones],
        }
        link = {"label": "재배치 계획 열기", "href": "/rebalancing"}

    elif parsed.intent == "surge":
        top = stats["top_surge_zones"]
        if top:
            names = ", ".join(f"{z['ko']}({signed_delta(z['forecast_delta'])})" for z in top)
            answer = f"수요가 급증한 지역: {names} (시간당 departures Δ). 이벤트로 인한 상승입니다."
        else:
            answer = "지금은 수요가 급증한 지역이 없어요."
        facts = {
            "affected_zone_count": stats["affected_zone_count"],
            "top_surge_zones": [
                {"ko": z["ko"], "forecast_delta": z["forecast_delta"]} for z in top
            ],
        }
        link = {"label": "운영 통계 열기", "href": "/statistics"}

    elif parsed.intent == "events":
        events = engine.available_events(cutoff)
        if events:
            titles = "; ".join(f"{i + 1}) {e.event_title}" for i, e in enumerate(events))
            answer = f"반영된 이벤트 {len(events)}건: {titles}."
        else:
            answer = "현재 시각 기준 공개된 이벤트가 없어요."
        facts = {
            "available_event_count": stats["available_event_count"],
            "events_by_type": stats["events_by_type"],
        }
        link = {"label": "뉴스 검색 열기", "href": "/news"}

    elif parsed.intent == "pricing":
        pricing = pricing_quotes(engine, cutoff)
        surcharged = [q for q in pricing["quotes"] if q["scarcity_surcharge"] > 0]
        credited = [q for q in pricing["quotes"] if q["balancing_credit"] > 0]
        max_tier = max((q["tier_multiplier"] for q in pricing["quotes"]), default=1.0)
        answer = (
            f"[SIMULATED · SHADOW] 할증 적용 {len(surcharged)}곳 (최대 ×{max_tier:.2f}), "
            f"균형 크레딧 {len(credited)}곳. 실제 라이더에게 적용되지 않는 시뮬레이션입니다."
        )
        facts = {
            "is_simulated": True,
            "surcharged_count": len(surcharged),
            "credited_count": len(credited),
            "max_tier_multiplier": max_tier,
        }
        link = {"label": "요금 시뮬레이터 열기", "href": "/pricing"}

    elif parsed.intent == "rebalance":
        answer = (
            f"지금 총 부족 {stats['total_shortage_units']}대 "
            f"({stats['stations_in_shortage']}곳)입니다. 재배치 계획에서 이동 또는 추가 "
            "자전거 최적 분배로 보완할 수 있어요."
        )
        facts = {
            "total_shortage_units": stats["total_shortage_units"],
            "stations_in_shortage": stats["stations_in_shortage"],
        }
        link = {"label": "재배치 계획 열기", "href": "/rebalancing"}

    elif parsed.intent == "navigate" and parsed.target_path:
        labels = {
            "/statistics": "운영 통계",
            "/rebalancing": "재배치 계획",
            "/pricing": "요금 시뮬레이터",
            "/news": "뉴스 검색",
            "/anomaly": "이상 탐지",
            "/experiment": "실험 랩",
            "/scenario": "시나리오 비교",
            "/why": "수요 급증 원인",
        }
        label = labels.get(parsed.target_path, parsed.target_path)
        answer = f"{label} 화면으로 이동할게요."
        link = {"label": f"{label} 열기", "href": parsed.target_path}

    elif parsed.intent == "help":
        answer = (
            "전체 현황, 부족 대여소, 수요 급증, 이벤트, 요금(시뮬레이션), 재배치를 알려드리고 관련 "
            "화면으로 바로 이동할 수 있어요. 예: '지금 현황 알려줘', '부족한 곳 어디야', "
            "'요금 화면 열어'."
        )

    else:  # unknown -> clarification, never a fabricated answer
        supported = False
        answer = (
            "질문을 이해하지 못했어요. 전체 현황, 부족 대여소, 수요 급증, 이벤트, 요금, 재배치를 "
            "물어봐 주세요. 예: '지금 시스템 현황 어때?'"
        )

    return {
        "mode": engine.mode,
        "cutoff": engine.cutoff,
        "model_version": engine.model_version,
        "query": query,
        "intent": parsed.intent,
        "supported": supported,
        "answer": answer,
        "facts": facts,
        "link": link,
        "note": (
            "규칙 기반(비-LLM) 운영 도우미입니다. 모든 수치는 대시보드와 동일한 API artifact"
            "(operator_statistics / pricing_quotes)에서 그대로 가져오며, 임의 SQL은 실행하지 "
            "않습니다(허용된 의도만). 이해하지 못한 질문에는 답을 지어내지 않고 되물어봅니다."
        ),
    }


def signed_delta(x: float) -> str:
    """'+3.9' / '-1.2' formatting for a demand delta (copilot verbalisation helper)."""
    v = f"{x:.1f}"
    return f"+{v}" if x > 0 else v


def hybrid_search(
    engine: ReplayEngine,
    query: str,
    cutoff: datetime,
    *,
    lat: float | None = None,
    lng: float | None = None,
    k: int = 10,
) -> dict:
    """V2-03 hybrid geo-semantic search, hydrated with as-of live inventory.

    Ranking comes from the search provider (BM25 + vector + geo, RRF); the authoritative live
    numbers are re-hydrated from the operational store (station_views) — never taken from the
    search index. Elastic degrades to the offline local provider when unavailable.
    """
    from config.search_v2 import load_search_config
    from ml.search import build_search_provider

    handle = build_search_provider(load_search_config())
    hits = handle.provider.search(query, lat=lat, lng=lng, k=k)
    by_id = _views_by_id(station_views(engine, cutoff))

    results = []
    for h in hits:
        row: dict = {
            "doc_id": h.doc_id,
            "kind": h.kind,
            "title": h.title,
            "score": round(h.score, 6),
            "distance_km": h.distance_km,
            "components": h.components,
        }
        if h.kind == "station" and h.station_id in by_id:
            v = by_id[h.station_id]
            row["station"] = _view_out(v)  # live inventory hydrated from the operational store
        results.append(row)

    return {
        "mode": engine.mode,
        "cutoff": engine.cutoff,
        "query": query,
        "provider": handle.provider.name,
        "degraded": handle.degraded,
        "provider_reason": handle.reason,
        "geo": {"lat": lat, "lng": lng} if lat is not None and lng is not None else None,
        "count": len(results),
        "results": results,
        "note": (
            "하이브리드 검색(BM25 + 문자 n-gram 벡터 + geo, RRF 융합) 순위입니다. 실시간 "
            "재고/가격의 source of truth는 운영 store이며, 검색 인덱스 값이 아니라 as-of 재고로 "
            "hydrate합니다. Elasticsearch가 없으면 오프라인 local provider로 degrade합니다."
        ),
    }

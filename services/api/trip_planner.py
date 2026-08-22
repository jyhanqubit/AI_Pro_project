"""V2-07 (rider) — trip planner: walk → rent → bike → return → walk.

Given an origin and a destination (both resolved to known places in the offline gazetteer), pick the
best RENT station near the origin that actually has bikes and the best RETURN station near the
destination that actually has free docks, then lay out the three legs with distances and times.

Division of labour (V2 contract): **all numbers here are deterministic** — station choice, distances
(`haversine_km`), and times come from the as-of inventory + geometry, never from an LLM. The LLM's
role (in `rider_copilot`) is only to (1) parse the natural-language request into origin/destination
and (2) narrate this typed plan; it never invents a station, distance, or time.

Honest limits, surfaced in the response:
- distances are straight-line (haversine) approximations, not street routing;
- only gazetteer-known places resolve (no arbitrary-address geocoding);
- inventory is as-of the replay cutoff (demo/historical), not live.
"""

from __future__ import annotations

from datetime import datetime

from pipelines.features.kernels import haversine_km

WALK_KMH = 4.8
BIKE_KMH = 15.0
_TIGHT_BIKES = 3    # rent station considered tight at/below this many bikes
_TIGHT_DOCKS = 3    # return station considered tight at/below this many free docks


def _leg_minutes(km: float, kmh: float) -> int:
    return int(round(km / kmh * 60)) if kmh > 0 else 0


def plan_trip(engine, cutoff: datetime, origin_id: str, destination_id: str) -> dict:
    """Plan origin→rent→bike→return→destination from the as-of station inventory."""
    from .v2 import _views_by_id, station_views

    views = station_views(engine, cutoff)
    by_id = _views_by_id(views)
    base = {"mode": "historical_replay", "cutoff": cutoff.isoformat(),
            "disclaimer": "거리는 직선거리 근사(도로 경로 아님) · 재고는 과거 재생(as-of) 기준"}

    if origin_id not in by_id:
        return {**base, "feasible": False, "reason": "unknown_origin",
                "answer": "출발지를 알 수 없어요. 등록된 지역 이름으로 다시 알려주세요."}
    if destination_id not in by_id:
        return {**base, "feasible": False, "reason": "unknown_destination",
                "answer": "목적지를 알 수 없어요. 등록된 지역 이름으로 다시 알려주세요."}

    o, d = by_id[origin_id], by_id[destination_id]
    rentable = [v for v in views if v.bikes > 0]
    returnable = [v for v in views if v.docks_free > 0]
    if not rentable:
        return {**base, "feasible": False, "reason": "no_bikes_anywhere",
                "answer": "지금은 어느 대여소에도 자전거가 없어요."}
    if not returnable:
        return {**base, "feasible": False, "reason": "no_docks_anywhere",
                "answer": "지금은 어느 대여소에도 반납할 빈 칸이 없어요."}

    def hv(a, b) -> float:
        return haversine_km(a.lat, a.lng, b.lat, b.lng)

    rent = min(rentable, key=lambda v: hv(o, v))
    ret = min(returnable, key=lambda v: hv(d, v))
    walk1, bike, walk2 = hv(o, rent), hv(rent, ret), hv(ret, d)
    walk_min = _leg_minutes(walk1 + walk2, WALK_KMH)
    bike_min = _leg_minutes(bike, BIKE_KMH)

    warnings: list[str] = []
    if rent.bikes <= _TIGHT_BIKES:
        warnings.append(f"대여소 재고가 빠듯해요 ({rent.bikes}대) — 서두르세요.")
    if rent.demand_delta > 0.001:
        warnings.append("이벤트로 출발지 주변 수요가 늘고 있어요.")
    if ret.docks_free <= _TIGHT_DOCKS:
        warnings.append(f"반납소 빈 칸이 얼마 없어요 ({ret.docks_free}칸).")
    confidence = "low" if warnings else ("ok" if min(rent.bikes, ret.docks_free) < 6 else "good")

    answer = (
        f"{o.ko}에서 {d.ko}까지: "
        f"{'출발지 대여소' if rent.station_id == o.station_id else rent.ko}에서 자전거를 빌리고"
        f"({rent.bikes}대), {ret.ko}에 반납"
        f"({ret.docks_free}칸)한 뒤 목적지까지 걸어가세요. "
        f"총 도보 약 {walk_min}분 · 자전거 약 {bike_min}분."
    )
    if warnings:
        answer += " ⚠ " + " ".join(warnings)

    return {
        **base,
        "feasible": True,
        "origin": {"id": o.station_id, "ko": o.ko, "en": o.en},
        "destination": {"id": d.station_id, "ko": d.ko, "en": d.en},
        "segments": [
            {"kind": "walk", "from": o.ko, "to": rent.ko,
             "distance_m": int(round(walk1 * 1000)), "minutes": _leg_minutes(walk1, WALK_KMH)},
            {"kind": "bike", "from": rent.ko, "to": ret.ko,
             "distance_m": int(round(bike * 1000)), "minutes": bike_min},
            {"kind": "walk", "from": ret.ko, "to": d.ko,
             "distance_m": int(round(walk2 * 1000)), "minutes": _leg_minutes(walk2, WALK_KMH)},
        ],
        "rent_station": {"id": rent.station_id, "ko": rent.ko, "en": rent.en, "bikes": rent.bikes,
                         "level": rent.level, "level_label": rent.level_label},
        "return_station": {"id": ret.station_id, "ko": ret.ko, "en": ret.en,
                           "docks_free": ret.docks_free, "capacity": ret.capacity},
        "total_walk_minutes": walk_min,
        "bike_minutes": bike_min,
        "total_minutes": walk_min + bike_min,
        "confidence": confidence,
        "warnings": warnings,
        "answer": answer,
    }


def resolve_endpoints(query: str, aliases: dict[str, tuple[str, ...]]) -> tuple[str | None, str | None]:
    """Rule-based origin/destination extraction: find gazetteer place mentions in the query and use
    Korean particle cues (…에서/…인데 = origin, …까지/…가 = destination), else first/second by position.

    This is the seam where an LLM parser (when a key is configured) replaces the rule for robustness to
    paraphrase/typos — the measured V2-06 lesson that intent understanding is where the LLM adds value.
    """
    q = query.lower()
    hits: list[tuple[int, str]] = []  # (position, station_id)
    for sid, terms in aliases.items():
        pos = min((q.find(t) for t in terms if t and t in q), default=-1)
        if pos >= 0:
            hits.append((pos, sid))
    hits.sort()
    if len(hits) < 2:
        # single mention: treat as destination (rider usually names where they want to go)
        return (None, hits[0][1]) if hits else (None, None)
    origin, destination = hits[0][1], hits[1][1]
    # particle cue: if a "출발" marker (에서/인데/출발) sits before the 2nd mention, ordering is right;
    # if "까지/가고" attaches to the 1st mention, swap.
    dest_markers = ("까지", "가고", "가려", "로 가", "으로 가")
    first_pos = hits[0][0]
    if any((m in q) and (q.find(m) < hits[1][0]) and (q.find(m) >= first_pos) and (q.find(m) < first_pos + 6)
           for m in dest_markers):
        origin, destination = hits[1][1], hits[0][1]
    return origin, destination

"""Candidate generation for recommendation (V1_Prompt §13).

For a query, gather nearby stations (radius expansion until enough), apply RENT/RETURN feasibility
and a detour ceiling, and flag inventory freshness. Feasibility uses inventory when known; when a
station's inventory is unknown it is kept as a candidate but flagged (``inventory_known=False``) —
never dropped on fabricated data (invariant 6). The chosen station is marked ``is_positive`` so the
positive-in-candidate rate can be measured.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.recsys import RecsysConfig
from contracts.v1.enums import RecommendationMode
from pipelines.features.kernels import haversine_km

from .dataset import RecSample
from .stations import Station, StationMaster


@dataclass(frozen=True)
class Candidate:
    station_id: str
    distance_km: float  # query -> station
    detour_km: float  # extra distance vs the direct origin->station (RETURN); 0 for RENT
    feasible: bool
    inventory_known: bool
    is_positive: bool


def _feasible(station: Station, mode: RecommendationMode) -> bool:
    if not station.inventory_known:
        return True  # unknown inventory: keep as candidate, flagged elsewhere
    if mode == RecommendationMode.RENT:
        return station.is_renting and (station.bikes_available or 0) > 0
    return station.is_returning and (station.docks_available or 0) > 0


def generate_candidates(
    sample: RecSample, master: StationMaster, config: RecsysConfig | None = None
) -> list[Candidate]:
    cfg = config or RecsysConfig()
    radius = cfg.radius_km
    chosen = sample.chosen_station_id

    while True:
        cands: list[Candidate] = []
        for st in master.all():
            d = haversine_km(sample.query_lat, sample.query_lng, st.lat, st.lng)
            if d > radius and st.station_id != chosen:
                continue
            detour = 0.0
            if sample.mode == RecommendationMode.RETURN and sample.trip_origin_lat is not None:
                direct = haversine_km(
                    sample.trip_origin_lat, sample.trip_origin_lng, st.lat, st.lng  # type: ignore[arg-type]
                )
                detour = max(0.0, direct - 0.0)  # detour vs going straight to the station
                if detour > cfg.max_detour_km and st.station_id != chosen:
                    continue
            cands.append(
                Candidate(
                    station_id=st.station_id,
                    distance_km=round(d, 4),
                    detour_km=round(detour, 4),
                    feasible=_feasible(st, sample.mode),
                    inventory_known=st.inventory_known,
                    is_positive=st.station_id == chosen,
                )
            )
        if len(cands) >= cfg.min_candidates or radius >= cfg.max_radius_km:
            return sorted(cands, key=lambda c: c.distance_km)
        radius = min(radius + cfg.radius_expand_km, cfg.max_radius_km)

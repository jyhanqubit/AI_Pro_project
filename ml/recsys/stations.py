"""Station master derivation for recommendation (V1_Prompt §13).

Builds an effective station master (id -> name, coordinate, H3 zone) from Trip History, and
optionally merges a GBFS inventory snapshot. Stations absent from GBFS get an explicit
``inventory_known=False`` missing mask rather than a fabricated inventory (invariant 6).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from pipelines.features.zones import zone_for


@dataclass(frozen=True)
class Station:
    station_id: str
    name: str
    lat: float
    lng: float
    zone_id: str
    capacity: int | None = None
    bikes_available: int | None = None
    docks_available: int | None = None
    is_renting: bool = True
    is_returning: bool = True
    inventory_known: bool = False


class StationMaster:
    """Immutable lookup of stations by id, with geographic helpers."""

    def __init__(self, stations: dict[str, Station]) -> None:
        self._stations = stations

    def __len__(self) -> int:
        return len(self._stations)

    def __contains__(self, station_id: str) -> bool:
        return station_id in self._stations

    def get(self, station_id: str) -> Station | None:
        return self._stations.get(station_id)

    def all(self) -> list[Station]:
        return list(self._stations.values())

    def ids(self) -> list[str]:
        return list(self._stations.keys())


def _mode_coord(series: pd.Series) -> float:
    """Most frequent coordinate for a station (robust to per-trip GPS noise)."""
    return float(series.round(5).mode().iloc[0])


def build_station_master(
    trips: pd.DataFrame,
    gbfs_status_path: str | Path | None = None,
) -> StationMaster:
    """Derive the station master from trips; merge GBFS inventory when a snapshot is given.

    ``trips`` must have start/end station id, name, lat, lng columns (Citi Bike schema).
    """
    frames = []
    for side in ("start", "end"):
        cols = {
            f"{side}_station_id": "station_id",
            f"{side}_station_name": "name",
            f"{side}_lat": "lat",
            f"{side}_lng": "lng",
        }
        if not all(c in trips.columns for c in cols):
            continue
        frames.append(trips[list(cols)].rename(columns=cols))
    if not frames:
        raise ValueError("trips frame has no recognisable station columns")

    obs = pd.concat(frames, ignore_index=True).dropna(subset=["station_id", "lat", "lng"])
    obs["station_id"] = obs["station_id"].astype(str)
    # Drop physically impossible coordinates (the fixtures include 999/NaN as bad-data cases).
    obs = obs[obs["lat"].between(-90, 90) & obs["lng"].between(-180, 180)]

    stations: dict[str, Station] = {}
    for sid, grp in obs.groupby("station_id"):
        lat = _mode_coord(grp["lat"])
        lng = _mode_coord(grp["lng"])
        name = str(grp["name"].mode().iloc[0])
        stations[sid] = Station(
            station_id=sid, name=name, lat=lat, lng=lng, zone_id=zone_for(lat, lng)
        )

    if gbfs_status_path is not None:
        _merge_gbfs(stations, Path(gbfs_status_path))
    return StationMaster(stations)


def _merge_gbfs(stations: dict[str, Station], path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for s in payload.get("data", {}).get("stations", []):
        sid = str(s["station_id"])
        if sid not in stations:
            continue  # GBFS may cover stations not seen in this trip slice; skip unknown geo
        base = stations[sid]
        bikes = int(s.get("num_bikes_available", 0))
        docks = int(s.get("num_docks_available", 0))
        stations[sid] = Station(
            station_id=base.station_id,
            name=base.name,
            lat=base.lat,
            lng=base.lng,
            zone_id=base.zone_id,
            capacity=bikes + docks,
            bikes_available=bikes,
            docks_available=docks,
            is_renting=bool(s.get("is_renting", 1)),
            is_returning=bool(s.get("is_returning", 1)),
            inventory_known=True,
        )

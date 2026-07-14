"""RENT/RETURN recommendation dataset from Trip History (V1_Prompt §13).

Each trip yields two supervised samples:
  - RENT  : the rider chose the START station to rent  -> positive = start_station_id
  - RETURN: the rider chose the END station to return  -> positive = end_station_id

The rider's exact origin is not in the data, so the query location is the positive station
coordinate perturbed by *deterministic* geographic jitter (seeded by ride id). The chosen station
id is the label and NEVER a query feature (leakage guard). Splitting is strictly chronological.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from config.recsys import RecsysConfig
from contracts.v1.enums import RecommendationMode

_M_PER_DEG_LAT = 111_320.0


def _valid_coord(lat: float, lng: float) -> bool:
    """Reject missing/out-of-range coordinates (the fixtures include NaN and 999 on purpose)."""
    return (
        lat == lat  # not NaN
        and lng == lng
        and -90.0 <= lat <= 90.0
        and -180.0 <= lng <= 180.0
    )


def _det_unit(key: str) -> tuple[float, float]:
    """Deterministic pseudo-random pair in [-1, 1) from a string key (seed-stable)."""
    h = hashlib.sha256(key.encode("utf-8")).digest()
    a = int.from_bytes(h[:8], "big") / 2**64  # [0,1)
    b = int.from_bytes(h[8:16], "big") / 2**64
    return a * 2 - 1, b * 2 - 1


def _jitter(lat: float, lng: float, key: str, max_m: float) -> tuple[float, float]:
    """Offset a coordinate by up to ``max_m`` metres, deterministically from ``key``."""
    du, dv = _det_unit(key)
    dlat = (du * max_m) / _M_PER_DEG_LAT
    dlng = (dv * max_m) / (_M_PER_DEG_LAT * math.cos(math.radians(lat)) or 1.0)
    return lat + dlat, lng + dlng


@dataclass(frozen=True)
class RecSample:
    """One (query -> chosen station) training/eval example. Query holds NO chosen-station id."""

    sample_id: str
    mode: RecommendationMode
    cutoff: datetime  # = trip start time; features must be as-of this
    query_lat: float  # jittered origin/destination — NOT the station coordinate
    query_lng: float
    hour: int
    dow: int  # day of week 0=Mon
    is_member: bool
    # Label (kept OUT of any query-feature vector):
    chosen_station_id: str
    query_is_synthetic: bool = True
    label_source: str = "historical_choice_with_synthetic_query"
    # For RETURN, the trip origin (to score detour); None for RENT.
    trip_origin_lat: float | None = None
    trip_origin_lng: float | None = None

    def query_features(self) -> dict[str, float]:
        """The query-side numeric features. Deliberately excludes ``chosen_station_id``."""
        return {
            "query_lat": self.query_lat,
            "query_lng": self.query_lng,
            "hour": float(self.hour),
            "dow": float(self.dow),
            "is_member": float(self.is_member),
            "is_return": float(self.mode == RecommendationMode.RETURN),
        }


def _parse_dt(v: object) -> datetime:
    ts = pd.Timestamp(v)
    if ts.tzinfo is None:
        ts = ts.tz_localize("America/New_York")
    return ts.to_pydatetime()


def build_dataset(
    trips: pd.DataFrame,
    config: RecsysConfig | None = None,
    modes: tuple[RecommendationMode, ...] = (RecommendationMode.RENT, RecommendationMode.RETURN),
) -> list[RecSample]:
    """Build RENT/RETURN samples. Deterministic given the same trips + config (invariant 14)."""
    cfg = config or RecsysConfig()
    samples: list[RecSample] = []
    for row in trips.itertuples(index=False):
        rid = str(row.ride_id)
        member = str(getattr(row, "member_casual", "member")).lower() == "member"
        slat, slng = float(row.start_lat), float(row.start_lng)
        elat, elng = float(row.end_lat), float(row.end_lng)
        if RecommendationMode.RENT in modes and _valid_coord(slat, slng):
            samples.append(
                _make(rid, RecommendationMode.RENT, cfg, member,
                      started_at=row.started_at,
                      station_id=str(row.start_station_id), slat=slat, slng=slng)
            )
        # RETURN needs a valid destination; the origin is optional (only used for detour).
        if RecommendationMode.RETURN in modes and _valid_coord(elat, elng):
            samples.append(
                _make(rid, RecommendationMode.RETURN, cfg, member,
                      started_at=row.started_at,
                      station_id=str(row.end_station_id), slat=elat, slng=elng,
                      origin_lat=slat if _valid_coord(slat, slng) else None,
                      origin_lng=slng if _valid_coord(slat, slng) else None)
            )
    return samples


def _make(
    rid: str, mode: RecommendationMode, cfg: RecsysConfig, member: bool, *,
    started_at: object, station_id: str, slat: float, slng: float,
    origin_lat: float | None = None, origin_lng: float | None = None,
) -> RecSample:
    cutoff = _parse_dt(started_at)
    qlat, qlng = _jitter(slat, slng, f"{rid}:{mode.value}:{cfg.seed}", cfg.jitter_max_m)
    return RecSample(
        sample_id=f"{rid}:{mode.value}",
        mode=mode,
        cutoff=cutoff,
        query_lat=qlat,
        query_lng=qlng,
        hour=cutoff.hour,
        dow=cutoff.weekday(),
        is_member=member,
        chosen_station_id=station_id,
        trip_origin_lat=origin_lat,
        trip_origin_lng=origin_lng,
    )


def chronological_split(
    samples: list[RecSample], test_fraction: float = 0.2
) -> tuple[list[RecSample], list[RecSample]]:
    """Split by cutoff time: earliest (1-frac) train, latest frac test. Never random (§13)."""
    ordered = sorted(samples, key=lambda s: s.cutoff)
    n_test = max(1, int(round(len(ordered) * test_fraction))) if ordered else 0
    split = len(ordered) - n_test
    return ordered[:split], ordered[split:]

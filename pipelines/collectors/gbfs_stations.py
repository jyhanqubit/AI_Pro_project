"""Import the real Citi Bike station network from GBFS ``station_information`` (V2).

GBFS ``station_information.json`` is a free, key-less feed listing every real Citi Bike station with
its coordinates, name, and dock capacity. This module fetches and parses it into the app's station
shape so the network can be populated from live data instead of a curated fixture.

A network/API failure returns a ``StationImportUnavailable`` (the caller degrades) — Demo Mode is
never broken. Fixture parsing is offline and deterministic so tests never touch the internet.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen

from config.collectors import (
    GBFS_LIVE_TIMEOUT_SECONDS,
    GBFS_STATION_INFORMATION_URL,
)


class StationImportUnavailable(RuntimeError):
    """Raised when the live GBFS station feed is unreachable (degraded, not fabricated)."""


@dataclass(frozen=True)
class BBox:
    """Optional geographic filter (lat/lng bounds) to import one region, not the whole city."""

    lat_min: float
    lat_max: float
    lng_min: float
    lng_max: float

    def contains(self, lat: float, lng: float) -> bool:
        return self.lat_min <= lat <= self.lat_max and self.lng_min <= lng <= self.lng_max


def parse_station_information(
    raw: bytes, *, bbox: BBox | None = None, limit: int = 0
) -> list[dict]:
    """Parse a GBFS station_information payload into station dicts (offline, deterministic)."""
    payload = json.loads(raw)
    out: list[dict] = []
    for s in payload.get("data", {}).get("stations", []):
        try:
            lat = float(s["lat"])
            lng = float(s["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if bbox is not None and not bbox.contains(lat, lng):
            continue
        capacity = int(s.get("capacity", 0) or 0)
        if capacity <= 0:
            continue
        out.append(
            {
                "station_id": str(s["station_id"]),
                "name": str(s.get("name", s["station_id"])),
                "lat": round(lat, 6),
                "lng": round(lng, 6),
                "capacity": capacity,
                # base_target: a sane default (≈40% of docks) until real demand tuning is available.
                "base_target": max(1, round(capacity * 0.4)),
            }
        )
    # Deterministic order (by id) so repeated imports are stable; apply an optional cap.
    out.sort(key=lambda d: d["station_id"])
    return out[:limit] if limit and limit > 0 else out


def fetch_station_information(
    *,
    url: str = GBFS_STATION_INFORMATION_URL,
    timeout: float = GBFS_LIVE_TIMEOUT_SECONDS,
    retries: int = 2,
    bbox: BBox | None = None,
    limit: int = 0,
) -> list[dict]:
    """Fetch + parse the live GBFS station network. Raises ``StationImportUnavailable`` if down."""
    last: Exception | None = None
    for _ in range(max(1, retries)):
        try:
            req = Request(url, headers={"User-Agent": "ShockFlowAI/1.0 research"})
            with urlopen(req, timeout=timeout) as r:  # noqa: S310 (trusted GBFS URL)
                raw = r.read()
            return parse_station_information(raw, bbox=bbox, limit=limit)
        except (URLError, TimeoutError, ValueError, KeyError, OSError) as e:
            last = e
    raise StationImportUnavailable(f"GBFS station_information fetch failed: {last}")

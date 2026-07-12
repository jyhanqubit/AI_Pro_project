"""H3 zone assignment. CLAUDE.md section 4 (primary grain is H3 zone x local hour).

Thin wrapper over the H3 library so the rest of the pipeline depends on a small, stable
surface. Supports both the v4 (``latlng_to_cell``) and v3 (``geo_to_h3``) function names.
"""

from __future__ import annotations

import h3

from config.features import H3_RESOLUTION

try:  # h3 v4
    _latlng_to_cell = h3.latlng_to_cell
    _cell_to_latlng = h3.cell_to_latlng
except AttributeError:  # pragma: no cover - h3 v3 fallback
    _latlng_to_cell = h3.geo_to_h3
    _cell_to_latlng = h3.h3_to_geo


def zone_for(lat: float, lng: float, resolution: int = H3_RESOLUTION) -> str:
    """Return the H3 cell id containing the given coordinate."""
    return _latlng_to_cell(lat, lng, resolution)


def zone_center(zone: str) -> tuple[float, float]:
    """Return the (latitude, longitude) of an H3 cell centre."""
    lat, lng = _cell_to_latlng(zone)
    return float(lat), float(lng)


def zone_neighbors(zone: str, k: int = 1) -> set[str]:
    """H3 cells within k rings of ``zone``, excluding the zone itself."""
    return set(h3.grid_disk(zone, k)) - {zone}

"""H3 zone assignment. CLAUDE.md section 4 (primary grain is H3 zone x local hour).

Thin wrapper over the H3 library so the rest of the pipeline depends on a small, stable
surface. Supports both the v4 (``latlng_to_cell``) and v3 (``geo_to_h3``) function names.
"""

from __future__ import annotations

import h3

from config.features import H3_RESOLUTION

try:  # h3 v4
    _latlng_to_cell = h3.latlng_to_cell
except AttributeError:  # pragma: no cover - h3 v3 fallback
    _latlng_to_cell = h3.geo_to_h3


def zone_for(lat: float, lng: float, resolution: int = H3_RESOLUTION) -> str:
    """Return the H3 cell id containing the given coordinate."""
    return _latlng_to_cell(lat, lng, resolution)

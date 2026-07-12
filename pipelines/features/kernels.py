"""Pure mathematical kernels for graph features. CLAUDE.md section 10.

Small, deterministic, side-effect-free functions: geographic distance, exponential distance
decay, and half-life temporal decay. Kept pure so they are trivially unit-testable and a
parameter change produces a reproducible feature change.
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two lat/lng points, in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def exp_distance_decay(distance_km: float, scale_km: float) -> float:
    """Influence weight in (0, 1] that falls off exponentially with distance."""
    if scale_km <= 0:
        raise ValueError("scale_km must be positive")
    return math.exp(-max(distance_km, 0.0) / scale_km)


def half_life_weight(age_hours: float, half_life_hours: float) -> float:
    """Temporal weight that halves every ``half_life_hours``; 0 for future ages."""
    if half_life_hours <= 0:
        raise ValueError("half_life_hours must be positive")
    if age_hours < 0:
        return 0.0
    return 0.5 ** (age_hours / half_life_hours)

"""As-of graph feature configuration. CLAUDE.md sections 10 and 5.

Domain parameters (half-life, geographic radius, decay scale, hops, source weights) live
here so a feature change caused by a parameter change is reproducible from configuration
(section 10). The feature version is bumped whenever the kernel or defaults change.
"""

from __future__ import annotations

from contracts.enums import EventType

FEATURE_VERSION = "gfv1"

# Count windows (hours before the cutoff) for event_count_*_by_type.
EVENT_COUNT_WINDOWS_H: tuple[int, ...] = (6, 24)

# Temporal decay: event influence halves every N hours. Per-type override, else default.
DEFAULT_HALF_LIFE_H = 6.0
HALF_LIFE_BY_TYPE_H: dict[EventType, float] = {
    EventType.TRANSIT_DISRUPTION: 6.0,
    EventType.WEATHER_SHOCK: 12.0,
    EventType.LARGE_VENUE_EVENT: 4.0,
    EventType.ROAD_CLOSURE: 8.0,
    EventType.PUBLIC_GATHERING: 4.0,
    EventType.SAFETY_INCIDENT: 6.0,
    EventType.SYSTEM_ALERT: 3.0,
}

# Spatial: only events within this radius (km) of a zone centre influence it; influence
# decays exponentially with a characteristic scale (km).
GEO_RADIUS_KM = 2.0
DISTANCE_DECAY_SCALE_KM = 1.0

# Graph propagation from adjacent H3 zones (neighbour_zone_impact).
MAX_GRAPH_HOPS = 1
NEIGHBOR_HOP_PENALTY = 0.5

# Per-source trust weight for source_weighted_severity (default 1.0 when absent).
SOURCE_WEIGHTS: dict[str, float] = {}
DEFAULT_SOURCE_WEIGHT = 1.0

# Only accepted extractions at/above this confidence contribute to features.
MIN_CONFIDENCE = 0.5

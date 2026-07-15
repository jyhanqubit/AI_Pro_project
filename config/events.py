"""Event extraction configuration. CLAUDE.md sections 8 and 6.3.

Keyword ontology, per-type demand/capacity effect priors, confidence thresholds, and dedup
settings live here so the mock provider is deterministic and its behavior is reproducible
from configuration (section 8: same fixture + prompt version -> same output).
"""

from __future__ import annotations

from contracts.enums import EffectDirection, EventType

# Prompt/model versioning carried on every extraction (section 8).
PROMPT_VERSION = "mock-v1"
# Prompt version for the real (opt-in) Anthropic provider; kept distinct from the mock so a
# stored extraction's provenance always identifies which extractor produced it.
ANTHROPIC_PROMPT_VERSION = "anthropic-extract-v1"

# Confidence handling (section 8): below threshold is rejected or quarantined.
CONFIDENCE_THRESHOLD = 0.5
LOW_CONFIDENCE_ACTION = "quarantine"  # "quarantine" | "reject"

# Bounded retries for malformed structured output (section 8).
MAX_EXTRACTION_RETRIES = 2

# Deduplication: token Jaccard on titles of same-type events (section 8, configurable/tested).
DEDUP_JACCARD_THRESHOLD = 0.6

# Trigger phrases per event type (matched case-insensitively over title + text).
EVENT_KEYWORDS: dict[EventType, tuple[str, ...]] = {
    EventType.TRANSIT_DISRUPTION: (
        "signal failure",
        "suspend",
        "service change",
        "no service",
        "single tracking",
        "delays",
        "disruption",
    ),
    EventType.WEATHER_SHOCK: (
        "storm",
        "heavy rain",
        "snow",
        "flooding",
        "heat advisory",
        "hurricane",
    ),
    EventType.LARGE_VENUE_EVENT: (
        "concert",
        "festival",
        "stadium",
        "arena",
        "sold out",
        "match",
    ),
    EventType.ROAD_CLOSURE: ("road closure", "street closed", "closed to traffic", "detour"),
    EventType.PUBLIC_GATHERING: ("protest", "parade", "rally", "march", "demonstration"),
    EventType.SAFETY_INCIDENT: ("accident", "fire", "evacuat", "police incident"),
    EventType.SYSTEM_ALERT: ("system alert", "planned maintenance", "outage"),
}

# Prior effect on (bike demand, dock capacity) per event type. Directional only — never a
# numeric percentage (section 8). e.g. transit down -> riders switch to bikes (demand up).
EVENT_EFFECT: dict[EventType, tuple[EffectDirection, EffectDirection]] = {
    EventType.TRANSIT_DISRUPTION: (EffectDirection.INCREASE, EffectDirection.UNKNOWN),
    EventType.WEATHER_SHOCK: (EffectDirection.DECREASE, EffectDirection.UNKNOWN),
    EventType.LARGE_VENUE_EVENT: (EffectDirection.INCREASE, EffectDirection.DECREASE),
    EventType.ROAD_CLOSURE: (EffectDirection.UNKNOWN, EffectDirection.DECREASE),
    EventType.PUBLIC_GATHERING: (EffectDirection.INCREASE, EffectDirection.DECREASE),
    EventType.SAFETY_INCIDENT: (EffectDirection.DECREASE, EffectDirection.UNKNOWN),
    EventType.SYSTEM_ALERT: (EffectDirection.UNKNOWN, EffectDirection.UNKNOWN),
}

# Ordinal severity prior per type (bounded 0..1, not an observed effect).
BASE_SEVERITY: dict[EventType, float] = {
    EventType.TRANSIT_DISRUPTION: 0.7,
    EventType.WEATHER_SHOCK: 0.6,
    EventType.LARGE_VENUE_EVENT: 0.5,
    EventType.ROAD_CLOSURE: 0.4,
    EventType.PUBLIC_GATHERING: 0.5,
    EventType.SAFETY_INCIDENT: 0.6,
    EventType.SYSTEM_ALERT: 0.3,
}

"""Enumerations shared across ShockFlow AI data contracts.

Mirrors the controlled vocabularies defined in CLAUDE.md sections 3, 4, and 6.3.
"""

from __future__ import annotations

from enum import StrEnum


class OperatingMode(StrEnum):
    """CLAUDE.md section 3. Every record/response/view declares its mode."""

    DEMO_FIXTURE = "demo_fixture"
    HISTORICAL_REPLAY = "historical_replay"
    LIVE = "live"
    RESEARCH = "research"


class EventType(StrEnum):
    """Accepted event ontology, CLAUDE.md section 6.3."""

    TRANSIT_DISRUPTION = "TRANSIT_DISRUPTION"
    WEATHER_SHOCK = "WEATHER_SHOCK"
    LARGE_VENUE_EVENT = "LARGE_VENUE_EVENT"
    ROAD_CLOSURE = "ROAD_CLOSURE"
    PUBLIC_GATHERING = "PUBLIC_GATHERING"
    SAFETY_INCIDENT = "SAFETY_INCIDENT"
    SYSTEM_ALERT = "SYSTEM_ALERT"
    OTHER = "OTHER"


class EffectDirection(StrEnum):
    """Qualitative effect direction extracted by the LLM (never a numeric demand %)."""

    INCREASE = "increase"
    DECREASE = "decrease"
    UNKNOWN = "unknown"


class ExtractionStatus(StrEnum):
    """Lifecycle status of an extraction. Rejected/quarantined stay auditable (section 6.3)."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"


class TargetName(StrEnum):
    """Forecast targets, CLAUDE.md section 4."""

    DEPARTURES = "departures"
    ARRIVALS = "arrivals"
    NET_FLOW = "net_flow"


class RiderType(StrEnum):
    """Citi Bike membership class. Statistically strong demand-composition signal (docs/EDA.md)."""

    MEMBER = "member"
    CASUAL = "casual"

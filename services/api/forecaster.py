"""Deterministic demo forecaster for the replay UI. CLAUDE.md sections 13, 22.

This is NOT the measured Phase 06 model. It is a transparent, deterministic heuristic used only
to drive the Historical-Replay walkthrough: a synthetic diurnal baseline, plus an event-aware
adjustment that is a visible function of the real graph event-exposure feature. It is versioned
``demo-heuristic-v1`` so it can never be confused with the trained/measured forecaster. The
measured evaluation lives in Phase 06 (reports / README).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

from config.api import (
    DEMO_BASE_MAX,
    DEMO_BASE_MIN,
    DEMO_FORECAST_SENSITIVITY,
    DIURNAL_MULTIPLIER,
)
from config.features import LOCAL_TZ

_NY = ZoneInfo(LOCAL_TZ)


def zone_base_level(zone_id: str) -> float:
    """Deterministic per-zone base demand (departures/hour) from the zone id hash."""
    h = int(hashlib.sha1(zone_id.encode("utf-8")).hexdigest(), 16)
    frac = (h % 1000) / 999.0
    return round(DEMO_BASE_MIN + frac * (DEMO_BASE_MAX - DEMO_BASE_MIN), 2)


def baseline_forecast(zone_id: str, cutoff: datetime) -> float:
    """Synthetic diurnal baseline demand for the target hour (demo only)."""
    local_hour = cutoff.astimezone(_NY).hour
    mult = DIURNAL_MULTIPLIER.get(local_hour, 1.0)
    return round(zone_base_level(zone_id) * mult, 2)


def event_aware_forecast(baseline: float, signed_exposure: float) -> float:
    """Adjust the baseline by the (signed) graph event-exposure — a transparent demo rule.

    ``signed_exposure`` is positive when events push demand up (e.g. a transit disruption sends
    riders to bikes) and negative when they suppress it. The delta is a visible function of the
    real graph feature, not a fabricated number.
    """
    adjusted = baseline * (1.0 + DEMO_FORECAST_SENSITIVITY * signed_exposure)
    return round(max(0.0, adjusted), 2)

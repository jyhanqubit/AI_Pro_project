"""API / replay demo configuration. CLAUDE.md sections 3, 12, 13, 16.

The golden-path replay runs on the curated news fixture (2026-07-12). Demo Mode is offline and
needs no API key. The demo forecaster is a deterministic, clearly-labelled heuristic used only
for the UI walkthrough (Historical Replay) -- it is NOT the measured Phase 06 model and is
versioned separately so the two can never be confused (sections 13, 22).
"""

from __future__ import annotations

from datetime import datetime

# Golden-path replay window (the news fixture crosses the 13:59 -> 14:00 boundary, section 7.2).
DEMO_START = datetime.fromisoformat("2026-07-12T12:00:00-04:00")
DEMO_END = datetime.fromisoformat("2026-07-12T18:00:00-04:00")
DEFAULT_CUTOFF = datetime.fromisoformat("2026-07-12T13:59:00-04:00")

# Deterministic demo baseline demand (departures/hour) — a synthetic diurnal profile, NOT real
# trip counts. Per-zone base level is derived deterministically from the zone id.
DEMO_BASE_MIN = 5.0
DEMO_BASE_MAX = 14.0
# Hour-of-day (local) multiplier on the base level; rush hours peak (matches the EDA finding
# that weekday demand is driven by rush timing).
DIURNAL_MULTIPLIER: dict[int, float] = {
    0: 0.2,
    1: 0.15,
    2: 0.1,
    3: 0.1,
    4: 0.15,
    5: 0.3,
    6: 0.6,
    7: 1.3,
    8: 1.6,
    9: 1.2,
    10: 0.8,
    11: 0.85,
    12: 0.95,
    13: 0.9,
    14: 0.85,
    15: 0.95,
    16: 1.4,
    17: 1.7,
    18: 1.5,
    19: 1.1,
    20: 0.8,
    21: 0.6,
    22: 0.45,
    23: 0.3,
}

# Demo forecaster sensitivity: how strongly a unit of graph event-exposure moves the forecast.
# The event-aware forecast is baseline * (1 + SENSITIVITY * signed_exposure). Transparent and
# deterministic; the delta is a visible function of the real graph feature, not a fabricated KPI.
DEMO_FORECAST_SENSITIVITY = 0.6
DEMO_MODEL_VERSION = "demo-heuristic-v1"

# Forecast target surfaced by the demo API.
DEMO_TARGET = "departures"
DEMO_FORECAST_HORIZON_H = 1

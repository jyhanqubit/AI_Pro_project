"""Feature/aggregation configuration. CLAUDE.md sections 4, 5.3, 5.4, 16.

Domain parameters (H3 resolution, lag/rolling windows) live in configuration so that a
feature change caused by a parameter change is reproducible from config (section 10).
"""

from __future__ import annotations

# Local timezone for demand aggregation (section 5.3).
LOCAL_TZ = "America/New_York"

# H3 resolution for the zone grid (section 4). Res 9 ~ 174 m avg hex edge, a good fit
# for station-level Citi Bike demand without over-fragmenting.
H3_RESOLUTION = 9

# Forecast targets (section 4).
DEMAND_TARGETS: tuple[str, ...] = ("departures", "arrivals", "net_flow")

# Short prefixes used in feature names.
TARGET_PREFIX: dict[str, str] = {
    "departures": "dep",
    "arrivals": "arr",
    "net_flow": "net",
}

# Leakage-safe temporal features (section 5.4). Lags in hours; rolling windows in hours,
# always shifted by one step so the current target never enters its own feature.
LAG_HOURS: tuple[int, ...] = (1, 24, 168)  # previous hour, previous day, previous week
ROLLING_WINDOWS: tuple[int, ...] = (3, 24)  # trailing 3h and 24h means (shifted)

# EDA-derived features (see docs/EDA.md). All leakage-safe (use only hours < t).
# Momentum = short trailing mean / long trailing mean; > 1 flags a surge above baseline
# (directly relevant to event-aware demand shocks). Uses (short, long) hours.
MOMENTUM_WINDOWS: tuple[int, int] = (3, 24)

# Member-share composition lags (docs/STATISTICAL_TESTS.md): member share differs strongly by
# regime (weekday commute vs weekend leisure, Cohen's d = 2.72). Lagged to stay leakage-safe.
MEMBER_SHARE_LAGS: tuple[int, ...] = (24, 168)

# Calendar features (section 11.2, ablation B1). These describe the target hour itself and
# are known at forecast time, so they are not subject to leakage shifting.
MORNING_RUSH_HOURS: tuple[int, ...] = (7, 8, 9)
EVENING_RUSH_HOURS: tuple[int, ...] = (16, 17, 18)

"""Leakage-safe lag and rolling features. CLAUDE.md section 5.4.

For each zone the demand panel is reindexed onto a gap-free hourly grid (missing hours = 0
demand) so that a lag of k hours is exactly k steps back. Every feature at hour t is derived
strictly from hours < t: the current target value never enters its own lag or rolling window,
and rolling windows are shifted before aggregation. No feature ever wraps across zones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from config.features import (
    DEMAND_TARGETS,
    LAG_HOURS,
    LOCAL_TZ,
    MEMBER_SHARE_LAGS,
    MOMENTUM_WINDOWS,
    ROLLING_WINDOWS,
    TARGET_PREFIX,
)
from contracts.demand import DemandCell

from .calendar import calendar_features
from .temporal import UTC, dense_hourly_index


@dataclass
class DemandFeatureRow:
    """A feature-store row: labels (current actuals) plus leakage-safe lag features."""

    zone_id: str
    hour_start: datetime
    targets: dict[str, int]
    features: dict[str, float | None] = field(default_factory=dict)


def _series_for_zone(
    cells: list[DemandCell], tz: ZoneInfo
) -> tuple[list[datetime], dict[str, list[int]], dict[datetime, DemandCell]]:
    """Dense hourly index and per-target series for one zone (missing hours -> 0)."""
    observed = {c.hour_start.astimezone(UTC): c for c in cells}
    index = dense_hourly_index([c.hour_start for c in cells], tz)
    series: dict[str, list[int]] = {t: [] for t in DEMAND_TARGETS}
    for hour in index:
        cell = observed.get(hour.astimezone(UTC))
        for target in DEMAND_TARGETS:
            series[target].append(getattr(cell, target) if cell is not None else 0)
    return index, series, observed


def _member_share_series(
    index: list[datetime], observed: dict[datetime, DemandCell]
) -> list[float | None]:
    """Member fraction of departures per hour (None when unknown / no departures)."""
    out: list[float | None] = []
    for hour in index:
        cell = observed.get(hour.astimezone(UTC))
        if cell is None:
            out.append(None)
            continue
        known = cell.departures_member + cell.departures_casual
        out.append(cell.departures_member / known if known > 0 else None)
    return out


def build_demand_features(
    cells: list[DemandCell],
    *,
    local_tz: str = LOCAL_TZ,
    lag_hours: tuple[int, ...] = LAG_HOURS,
    rolling_windows: tuple[int, ...] = ROLLING_WINDOWS,
    momentum_windows: tuple[int, int] = MOMENTUM_WINDOWS,
    member_share_lags: tuple[int, ...] = MEMBER_SHARE_LAGS,
) -> list[DemandFeatureRow]:
    """Build leakage-safe lag/rolling features for observed demand cells."""
    tz = ZoneInfo(local_tz)
    by_zone: dict[str, list[DemandCell]] = {}
    for cell in cells:
        by_zone.setdefault(cell.zone_id, []).append(cell)

    rows: list[DemandFeatureRow] = []
    for zone, zone_cells in by_zone.items():
        index, series, observed = _series_for_zone(zone_cells, tz)
        member_share = _member_share_series(index, observed)
        for i, hour in enumerate(index):
            obs_cell = observed.get(hour.astimezone(UTC))
            if obs_cell is None:
                continue  # emit features only for observed hours
            feats: dict[str, float | None] = {}
            for target in DEMAND_TARGETS:
                s = series[target]
                prefix = TARGET_PREFIX[target]
                for k in lag_hours:
                    j = i - k
                    feats[f"{prefix}_lag_{k}"] = float(s[j]) if j >= 0 else None
                for w in rolling_windows:
                    # Shifted window: the w hours strictly before t, excluding t itself.
                    if i - w >= 0:
                        feats[f"{prefix}_roll_mean_{w}"] = sum(s[i - w : i]) / w
                    else:
                        feats[f"{prefix}_roll_mean_{w}"] = None

            # --- EDA-derived features (all use only hours < t) ---
            short_w, long_w = momentum_windows
            for target in ("departures", "arrivals"):
                s = series[target]
                prefix = TARGET_PREFIX[target]
                # Surge momentum: recent short mean vs longer baseline mean.
                if i - short_w >= 0 and i - long_w >= 0:
                    short_mean = sum(s[i - short_w : i]) / short_w
                    long_mean = sum(s[i - long_w : i]) / long_w
                    feats[f"{prefix}_momentum"] = short_mean / (long_mean + 1e-6)
                else:
                    feats[f"{prefix}_momentum"] = None
                # Zone level: expanding mean of all prior hours (running demand scale).
                feats[f"{prefix}_expanding_mean"] = (sum(s[:i]) / i) if i > 0 else None

            # Rebalancing pressure: net flow accumulated earlier in the same local day.
            net_series = series["net_flow"]
            today = hour.date()
            prior_today = [net_series[j] for j in range(i) if index[j].date() == today]
            feats["net_cumsum_day"] = float(sum(prior_today))

            # Demand composition (member share), lagged to stay leakage-safe (docs/EDA.md).
            for k in member_share_lags:
                j = i - k
                feats[f"member_share_lag_{k}"] = member_share[j] if j >= 0 else None

            # Calendar features describe the target hour and carry no leakage (11.2, B1).
            feats.update(calendar_features(hour))
            rows.append(
                DemandFeatureRow(
                    zone_id=zone,
                    hour_start=hour,
                    targets={t: getattr(obs_cell, t) for t in DEMAND_TARGETS},
                    features=feats,
                )
            )

    rows.sort(key=lambda r: (r.hour_start, r.zone_id))
    return rows

"""Demand aggregation and feature store (CLAUDE.md sections 4, 5.3, 5.4)."""

from __future__ import annotations

from .aggregate import aggregate_demand
from .calendar import calendar_features, us_federal_holidays
from .lags import DemandFeatureRow, build_demand_features
from .temporal import classify_local, dense_hourly_index, localize, to_local_hour
from .zones import zone_for

__all__ = [
    "aggregate_demand",
    "build_demand_features",
    "DemandFeatureRow",
    "zone_for",
    "localize",
    "classify_local",
    "to_local_hour",
    "dense_hourly_index",
    "calendar_features",
    "us_federal_holidays",
]

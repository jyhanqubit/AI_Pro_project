"""Demand aggregation and feature store (CLAUDE.md sections 4, 5.3, 5.4)."""

from __future__ import annotations

from .aggregate import aggregate_demand
from .calendar import calendar_features, us_federal_holidays
from .graph_features import GraphFeatureConfig, build_graph_features
from .kernels import exp_distance_decay, half_life_weight, haversine_km
from .lags import DemandFeatureRow, build_demand_features
from .temporal import classify_local, dense_hourly_index, localize, to_local_hour
from .zones import zone_center, zone_for, zone_neighbors

__all__ = [
    "aggregate_demand",
    "build_demand_features",
    "DemandFeatureRow",
    "build_graph_features",
    "GraphFeatureConfig",
    "haversine_km",
    "exp_distance_decay",
    "half_life_weight",
    "zone_for",
    "zone_center",
    "zone_neighbors",
    "localize",
    "classify_local",
    "to_local_hour",
    "dense_hourly_index",
    "calendar_features",
    "us_federal_holidays",
]

"""Anomaly-detection configuration (V1_Prompt §12)."""

from __future__ import annotations

from dataclasses import dataclass

ANOMALY_CONFIG_VERSION = "anomaly-v1"


@dataclass(frozen=True)
class AnomalyConfig:
    # data_quality
    freshness_max_minutes: float = 30.0  # snapshot older than this => stale feed
    # inventory (robust rolling z-score on bikes)
    rolling_window: int = 6
    depletion_z: float = 3.0  # |robust z| above this => sudden depletion/spike
    min_history: int = 4
    # forecast_residual
    residual_sigma: float = 2.5  # |actual - forecast| / scale above this => residual anomaly
    residual_scale_floor: float = 1.0
    # proxy_demand (optional Isolation Forest behind this flag; off by default, §12)
    enable_isolation_forest: bool = False
    version: str = ANOMALY_CONFIG_VERSION

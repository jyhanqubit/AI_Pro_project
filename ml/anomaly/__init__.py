"""Anomaly detection & root cause (V1_Prompt §12).

Four detector families over station-status observations: data_quality, inventory,
forecast_residual, proxy_demand. Root-cause attribution links an anomaly to source events when the
zone/time overlaps. Synthetic faults are flagged so they never masquerade as real incidents.
"""

from __future__ import annotations

from .detectors import StationObs, detect_all
from .root_cause import attribute_root_cause

__all__ = ["StationObs", "detect_all", "attribute_root_cause"]

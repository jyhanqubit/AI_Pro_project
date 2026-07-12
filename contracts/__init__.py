"""ShockFlow AI data contracts (CLAUDE.md section 6).

Typed Pydantic v2 models used at every service and pipeline boundary.
"""

from __future__ import annotations

from .article import ArticleRecord
from .common import ContractModel
from .demand import DemandCell
from .enums import (
    EffectDirection,
    EventType,
    ExtractionStatus,
    OperatingMode,
    TargetName,
)
from .event import EventExtraction, EvidenceSpan, Location
from .feature import FeatureSnapshot
from .forecast import ForecastOutput
from .station import StationStatusRecord
from .trip import TripRecord

__all__ = [
    "ContractModel",
    "OperatingMode",
    "EventType",
    "EffectDirection",
    "ExtractionStatus",
    "TargetName",
    "TripRecord",
    "ArticleRecord",
    "EventExtraction",
    "EvidenceSpan",
    "Location",
    "FeatureSnapshot",
    "ForecastOutput",
    "StationStatusRecord",
    "DemandCell",
]

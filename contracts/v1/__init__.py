"""ShockFlow AI V1 data contracts.

Additive, backward-compatible extension of the v0 contracts (``contracts/``). V1 introduces
recommendation, incentive, anomaly, and experimentation contracts plus an explicit
*claim boundary* — every predicted/serving artifact carries a ``ClaimState`` so measured,
pending-label, simulated, and dry-run results can never be conflated (V1_Prompt §4, §6).

Nothing here mutates the v0 contracts; the v0 ``OperatingMode`` and models are re-exported so
existing callers keep working (invariant 12: no breaking change without migration).
"""

from __future__ import annotations

from .anomaly import AnomalyAlert
from .enums import (
    AnomalyType,
    ClaimState,
    OperatingModeV1,
    RecommendationMode,
    RootCauseStatus,
)
from .experiment import ExperimentDefinition, ExposureLog, OutcomeLog
from .forecasting import ForecastPair, ScoredForecastPair
from .recommendation import (
    IncentiveQuote,
    RecommendationRequest,
    RecommendationResult,
)
from .records import ArticleRecord, EventRecordV1

__all__ = [
    "OperatingModeV1",
    "ClaimState",
    "RecommendationMode",
    "AnomalyType",
    "RootCauseStatus",
    "ArticleRecord",
    "EventRecordV1",
    "ForecastPair",
    "ScoredForecastPair",
    "AnomalyAlert",
    "RecommendationRequest",
    "RecommendationResult",
    "IncentiveQuote",
    "ExperimentDefinition",
    "ExposureLog",
    "OutcomeLog",
]

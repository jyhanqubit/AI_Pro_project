"""Forecast output contract. CLAUDE.md sections 6.5 and 4 (invariant 8).

Uncertainty quantiles are optional: omit or leave null when the model does not produce
calibrated intervals. Do not invent intervals (section 6.5).
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field, model_validator

from .common import ContractModel
from .enums import OperatingMode, TargetName


class ForecastOutput(ContractModel):
    zone_id: str = Field(min_length=1)
    forecast_cutoff: AwareDatetime
    forecast_horizon: int = Field(gt=0, description="Horizon in hours ahead of the cutoff.")
    model_version: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    target_name: TargetName
    baseline_forecast: float
    p10: float | None = Field(default=None, description="Optional; null if no calibrated interval.")
    p50: float | None = Field(default=None, description="Optional; null if no calibrated interval.")
    p90: float | None = Field(default=None, description="Optional; null if no calibrated interval.")
    event_aware_forecast: float
    forecast_delta: float | None = Field(
        default=None,
        description="event_aware_forecast - baseline_forecast; computed when omitted.",
    )
    mode: OperatingMode

    @model_validator(mode="after")
    def _validate(self) -> ForecastOutput:
        computed_delta = self.event_aware_forecast - self.baseline_forecast
        if self.forecast_delta is None:
            self.forecast_delta = computed_delta

        if self.p10 is not None and self.p50 is not None and self.p90 is not None:
            if not (self.p10 <= self.p50 <= self.p90):
                raise ValueError("quantiles must satisfy p10 <= p50 <= p90")
        return self

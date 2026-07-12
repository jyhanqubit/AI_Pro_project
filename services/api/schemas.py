"""API request/response models. CLAUDE.md section 12.

Every response carries its operating mode and, where relevant, the cutoff and model/feature
versions (section 12). Explanations always include provenance and evidence (never evidence-free,
sections 12, 13). Uncertainty intervals are omitted rather than invented (section 6.5).
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, Field

from contracts.enums import EffectDirection, EventType, OperatingMode, TargetName


class HealthResponse(BaseModel):
    status: str
    mode: OperatingMode
    cutoff: AwareDatetime
    model_version: str
    feature_version: str


class ReplayState(BaseModel):
    mode: OperatingMode
    cutoff: AwareDatetime
    window_start: AwareDatetime
    window_end: AwareDatetime
    available_event_count: int


class SetCutoffRequest(BaseModel):
    cutoff: AwareDatetime


class LocationOut(BaseModel):
    name: str
    lat: float | None = None
    lng: float | None = None


class EvidenceOut(BaseModel):
    article_id: str
    text: str


class EventOut(BaseModel):
    event_id: str
    event_type: EventType
    event_title: str
    event_summary: str
    available_at: AwareDatetime | None
    event_start_at: AwareDatetime | None
    demand_effect: EffectDirection
    severity: float
    confidence: float
    locations: list[LocationOut]
    source_article_ids: list[str]
    evidence_spans: list[EvidenceOut]


class EventsResponse(BaseModel):
    mode: OperatingMode
    cutoff: AwareDatetime
    events: list[EventOut]


class ForecastOut(BaseModel):
    zone_id: str
    forecast_cutoff: AwareDatetime
    forecast_horizon: int
    model_version: str
    feature_version: str
    target_name: TargetName
    baseline_forecast: float
    event_aware_forecast: float
    forecast_delta: float
    event_exposure: float
    mode: OperatingMode


class ForecastsResponse(BaseModel):
    mode: OperatingMode
    cutoff: AwareDatetime
    model_version: str
    feature_version: str
    target_name: TargetName
    forecasts: list[ForecastOut]


class TraceStep(BaseModel):
    """One Article -> Event -> H3Zone -> Feature provenance chain (section 13, Why Changed)."""

    event_id: str
    event_type: EventType
    event_title: str
    demand_effect: EffectDirection
    severity: float
    confidence: float
    source_article_ids: list[str]
    evidence_spans: list[EvidenceOut]
    contributed_features: dict[str, float]


class ExplanationResponse(BaseModel):
    mode: OperatingMode
    zone_id: str
    cutoff: AwareDatetime
    model_version: str
    feature_version: str
    baseline_forecast: float
    event_aware_forecast: float
    forecast_delta: float
    event_exposure: float
    drivers: list[TraceStep]
    note: str


class ScenarioRequest(BaseModel):
    cutoff: AwareDatetime | None = None
    disabled_event_ids: list[str] = Field(default_factory=list)


class ScenarioZone(BaseModel):
    zone_id: str
    baseline_forecast: float
    scenario_forecast: float
    default_event_aware_forecast: float
    scenario_delta: float


class ScenarioResponse(BaseModel):
    mode: OperatingMode
    cutoff: AwareDatetime
    disabled_event_ids: list[str]
    model_version: str
    feature_version: str
    zones: list[ScenarioZone]


class ErrorResponse(BaseModel):
    error_code: str
    message: str

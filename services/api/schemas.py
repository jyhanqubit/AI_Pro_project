"""API request/response models. CLAUDE.md section 12.

Every response carries its operating mode and, where relevant, the cutoff and model/feature
versions (section 12). Explanations always include provenance and evidence (never evidence-free,
sections 12, 13). Uncertainty intervals are omitted rather than invented (section 6.5).
"""

from __future__ import annotations

from typing import Literal

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


class RebalancingRequest(BaseModel):
    cutoff: AwareDatetime | None = None
    method: Literal["greedy", "milp"] = "milp"
    vehicle_capacity: int | None = Field(default=None, ge=0)


class MoveOut(BaseModel):
    origin_station_id: str
    destination_station_id: str
    quantity: int
    distance_km: float


class StationStateOut(BaseModel):
    station_id: str
    name: str
    zone_id: str
    bikes_before: int
    bikes_after: int
    target: int
    base_target: int
    capacity: int
    shortage_before: int
    shortage_after: int


class RebalancingResponse(BaseModel):
    mode: OperatingMode
    cutoff: AwareDatetime
    model_version: str
    method: str
    feasible: bool
    infeasibility_reason: str | None
    vehicle_capacity: int
    total_moved: int
    total_distance_km: float
    shortage_units_before: int
    shortage_units_after: int
    overflow_units_before: int
    overflow_units_after: int
    shortage_reduction: int
    overflow_reduction: int
    total_cost: float
    baseline_cost: float
    moves: list[MoveOut]
    stations: list[StationStateOut]
    note: str


class ErrorResponse(BaseModel):
    error_code: str
    message: str


class RecommendationApiRequest(BaseModel):
    """RENT/RETURN station recommendation query (V1_Prompt §15)."""

    mode: Literal["rent", "return"]
    lat: float = Field(ge=-90.0, le=90.0)
    lng: float = Field(ge=-180.0, le=180.0)
    is_member: bool = True
    cutoff: AwareDatetime | None = None


class ExtraBikeAllocationRequest(BaseModel):
    """Operator injects ``extra_bikes`` more bikes; allocate them optimally (V2)."""

    extra_bikes: int = Field(ge=0, le=1000, description="Extra bikes to inject into the network")
    cutoff: AwareDatetime | None = None


class RiderAskRequest(BaseModel):
    """A rider's natural-language query for the deterministic copilot (V2)."""

    query: str = Field(min_length=1, max_length=200)
    cutoff: AwareDatetime | None = None

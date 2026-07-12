"""FastAPI application. CLAUDE.md section 12.

Serves the offline replay demo: health, replay clock, as-of events, demo forecasts, evidence-
backed zone explanations, and scenario comparison. Every response carries its mode/cutoff and
model/feature versions. Rebalancing is deferred to Phase 08 and returns a clear 501, never a
fabricated success (sections 12, 22).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException

from config.api import DEMO_FORECAST_HORIZON_H
from contracts.enums import TargetName
from contracts.event import EventExtraction

from .replay import DEMO_WINDOW, Driver, ReplayEngine, ZoneForecast, get_engine
from .schemas import (
    ErrorResponse,
    EventOut,
    EventsResponse,
    EvidenceOut,
    ExplanationResponse,
    ForecastOut,
    ForecastsResponse,
    HealthResponse,
    LocationOut,
    ReplayState,
    ScenarioRequest,
    ScenarioResponse,
    ScenarioZone,
    SetCutoffRequest,
    TraceStep,
)

EngineDep = Annotated[ReplayEngine, Depends(get_engine)]
_TARGET = TargetName.DEPARTURES


def _event_out(e: EventExtraction) -> EventOut:
    return EventOut(
        event_id=e.event_id,
        event_type=e.event_type,
        event_title=e.event_title,
        event_summary=e.event_summary,
        available_at=e.available_at,
        event_start_at=e.event_start_at,
        demand_effect=e.demand_effect,
        severity=e.severity,
        confidence=e.confidence,
        locations=[LocationOut(name=loc.name, lat=loc.lat, lng=loc.lng) for loc in e.locations],
        source_article_ids=e.source_article_ids,
        evidence_spans=[
            EvidenceOut(article_id=s.article_id, text=s.text) for s in e.evidence_spans
        ],
    )


def _forecast_out(engine: ReplayEngine, zf: ZoneForecast, cutoff: datetime) -> ForecastOut:
    return ForecastOut(
        zone_id=zf.zone_id,
        forecast_cutoff=cutoff,
        forecast_horizon=DEMO_FORECAST_HORIZON_H,
        model_version=engine.model_version,
        feature_version=engine.feature_version,
        target_name=_TARGET,
        baseline_forecast=zf.baseline_forecast,
        event_aware_forecast=zf.event_aware_forecast,
        forecast_delta=zf.forecast_delta,
        event_exposure=zf.event_exposure,
        mode=engine.mode,
    )


def _trace_step(d: Driver) -> TraceStep:
    e = d.event
    return TraceStep(
        event_id=e.event_id,
        event_type=e.event_type,
        event_title=e.event_title,
        demand_effect=e.demand_effect,
        severity=e.severity,
        confidence=e.confidence,
        source_article_ids=e.source_article_ids,
        evidence_spans=[
            EvidenceOut(article_id=s.article_id, text=s.text) for s in e.evidence_spans
        ],
        contributed_features=d.contributed_features,
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="ShockFlow AI API",
        version="0.7.0",
        summary="Event-aware demand forecasting & rebalancing decision support (Phase 07).",
    )

    @app.get("/v1/health", response_model=HealthResponse)
    def health(engine: EngineDep) -> HealthResponse:
        return HealthResponse(
            status="ok",
            mode=engine.mode,
            cutoff=engine.cutoff,
            model_version=engine.model_version,
            feature_version=engine.feature_version,
        )

    @app.get("/v1/replay/state", response_model=ReplayState)
    def replay_state(engine: EngineDep) -> ReplayState:
        start, end = DEMO_WINDOW
        return ReplayState(
            mode=engine.mode,
            cutoff=engine.cutoff,
            window_start=start,
            window_end=end,
            available_event_count=len(engine.available_events()),
        )

    @app.post(
        "/v1/replay/set-cutoff",
        response_model=ReplayState,
        responses={400: {"model": ErrorResponse}},
    )
    def set_cutoff(body: SetCutoffRequest, engine: EngineDep) -> ReplayState:
        start, end = DEMO_WINDOW
        if not (start <= body.cutoff <= end):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "cutoff_out_of_window",
                    "message": f"cutoff must be within [{start.isoformat()}, {end.isoformat()}]",
                },
            )
        engine.set_cutoff(body.cutoff)
        return replay_state(engine)

    @app.get("/v1/events", response_model=EventsResponse)
    def events(engine: EngineDep) -> EventsResponse:
        avail = engine.available_events()
        return EventsResponse(
            mode=engine.mode,
            cutoff=engine.cutoff,
            events=[_event_out(e) for e in avail],
        )

    @app.get("/v1/forecasts", response_model=ForecastsResponse)
    def forecasts(engine: EngineDep) -> ForecastsResponse:
        zfs = engine.forecasts()
        return ForecastsResponse(
            mode=engine.mode,
            cutoff=engine.cutoff,
            model_version=engine.model_version,
            feature_version=engine.feature_version,
            target_name=_TARGET,
            forecasts=[_forecast_out(engine, zf, engine.cutoff) for zf in zfs],
        )

    @app.get(
        "/v1/zones/{zone_id}/explanation",
        response_model=ExplanationResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def explanation(zone_id: str, engine: EngineDep) -> ExplanationResponse:
        if zone_id not in engine.demo_zones:
            raise HTTPException(
                status_code=404,
                detail={"error_code": "zone_not_found", "message": f"unknown zone {zone_id}"},
            )
        zf = engine.zone_forecast(zone_id, engine.cutoff)
        drivers = engine.drivers(zone_id, engine.cutoff)
        note = (
            "Forecast from the demo heuristic (demo-heuristic-v1), Historical Replay; the delta "
            "is a transparent function of the graph event-exposure feature, not a trained-model "
            "output. Drivers show grounded evidence per event."
            if drivers
            else "No events available as-of this cutoff; event-aware forecast equals baseline."
        )
        assert zf is not None  # zone_id is a demo zone
        return ExplanationResponse(
            mode=engine.mode,
            zone_id=zone_id,
            cutoff=engine.cutoff,
            model_version=engine.model_version,
            feature_version=engine.feature_version,
            baseline_forecast=zf.baseline_forecast,
            event_aware_forecast=zf.event_aware_forecast,
            forecast_delta=zf.forecast_delta,
            event_exposure=zf.event_exposure,
            drivers=[_trace_step(d) for d in drivers],
            note=note,
        )

    @app.post("/v1/scenarios", response_model=ScenarioResponse)
    def scenarios(body: ScenarioRequest, engine: EngineDep) -> ScenarioResponse:
        cutoff = body.cutoff or engine.cutoff
        disabled = tuple(body.disabled_event_ids)
        default = {zf.zone_id: zf for zf in engine.forecasts(cutoff)}
        scenario = {zf.zone_id: zf for zf in engine.forecasts(cutoff, disabled)}
        zones = [
            ScenarioZone(
                zone_id=z,
                baseline_forecast=scenario[z].baseline_forecast,
                scenario_forecast=scenario[z].event_aware_forecast,
                default_event_aware_forecast=default[z].event_aware_forecast,
                scenario_delta=round(
                    scenario[z].event_aware_forecast - default[z].event_aware_forecast, 2
                ),
            )
            for z in engine.demo_zones
        ]
        return ScenarioResponse(
            mode=engine.mode,
            cutoff=cutoff,
            disabled_event_ids=list(body.disabled_event_ids),
            model_version=engine.model_version,
            feature_version=engine.feature_version,
            zones=zones,
        )

    @app.post("/v1/rebalancing/solve", responses={501: {"model": ErrorResponse}})
    def rebalancing_solve(engine: EngineDep) -> None:
        raise HTTPException(
            status_code=501,
            detail={
                "error_code": "not_implemented",
                "message": "Rebalancing is implemented in Phase 08 (classical + quantum research).",
            },
        )

    return app


app = create_app()

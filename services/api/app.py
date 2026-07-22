"""FastAPI application. CLAUDE.md section 12.

Serves the offline replay demo: health, replay clock, as-of events, demo forecasts, evidence-
backed zone explanations, and scenario comparison. Every response carries its mode/cutoff and
model/feature versions. Rebalancing is deferred to Phase 08 and returns a clear 501, never a
fabricated success (sections 12, 22).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config.api import DEMO_FORECAST_HORIZON_H
from contracts.enums import TargetName
from contracts.event import EventExtraction

from .rebalancing import solve as solve_rebalancing
from .replay import DEMO_WINDOW, Driver, ReplayEngine, ZoneForecast, get_engine
from .schemas import (
    ErrorResponse,
    EventOut,
    EventsResponse,
    EvidenceOut,
    ExplanationResponse,
    ExtraBikeAllocationRequest,
    ForecastOut,
    ForecastsResponse,
    HealthResponse,
    LocationOut,
    MoveOut,
    NewsSyncRequest,
    OpsAskRequest,
    PricingQuoteRequest,
    RebalancingRequest,
    RebalancingResponse,
    RecommendationApiRequest,
    ReplayState,
    RevenueRequest,
    RiderAskRequest,
    TripPlanRequest,
    ScenarioRequest,
    ScenarioResponse,
    ScenarioZone,
    SetCutoffRequest,
    StationStateOut,
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
        version="0.1.0",  # v0 milestone (Phases 00-08)
        summary="Event-aware demand forecasting & rebalancing decision support (Phase 08).",
    )

    # CORS. Local/LAN dev serves the Next.js UI on :3000 (localhost / 127.0.0.1 / the PC's LAN IP).
    # Any Vercel deployment (*.vercel.app, incl. preview URLs) is allowed by default so the hosted
    # frontend works without extra config; SHOCKFLOW_CORS_ORIGINS can add more exact origins
    # (e.g. a custom domain) as a comma-separated list.
    deployed_origins = [
        o.strip() for o in os.environ.get("SHOCKFLOW_CORS_ORIGINS", "").split(",") if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=deployed_origins,
        allow_origin_regex=r"http://[\w.-]+:3000|https://[\w-]+\.vercel\.app",
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
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
            "예보는 데모 heuristic(demo-heuristic-v1, 과거 재생)에서 나온 값입니다. "
            "변화(Δ)는 그래프 이벤트 노출 지표를 그대로 반영한 값이며, 학습된 모델의 "
            "출력이 아닙니다. 아래 항목은 이벤트별 근거를 보여줍니다."
            if drivers
            else (
                "현재 시각 기준으로 공개된 이벤트가 없어요. "
                "이벤트 반영 예보가 평상시 예보와 같습니다."
            )
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

    @app.post(
        "/v1/rebalancing/solve",
        response_model=RebalancingResponse,
        responses={400: {"model": ErrorResponse}},
    )
    def rebalancing_solve(
        engine: EngineDep, body: RebalancingRequest | None = None
    ) -> RebalancingResponse:
        req = body or RebalancingRequest()
        cutoff = req.cutoff or engine.cutoff
        start, end = DEMO_WINDOW
        if not (start <= cutoff <= end):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "cutoff_out_of_window",
                    "message": f"cutoff must be within [{start.isoformat()}, {end.isoformat()}]",
                },
            )
        sol = solve_rebalancing(
            engine, cutoff, method=req.method, vehicle_capacity=req.vehicle_capacity
        )
        note = (
            "큐레이션된 station fixture 위에서 동작하는 고전 solver입니다. 이벤트가 노출된 지역은 "
            "데모 heuristic 예보 델타(과거 재생)만큼 목표 재고가 올라가며, 측정된 Phase 06 모델이 "
            "아닙니다. 계획은 노출 전에 feasibility를 검증하며, Quantum Research Mode(QUBO/QAOA)는 "
            "운영 계획에 절대 사용하지 않습니다."
        )
        return RebalancingResponse(
            mode=engine.mode,
            cutoff=cutoff,
            model_version=engine.model_version,
            method=sol.method,
            feasible=sol.feasible,
            infeasibility_reason=sol.infeasibility_reason,
            vehicle_capacity=sol.vehicle_capacity,
            total_moved=sol.plan.total_moved,
            total_distance_km=sol.cost.distance_km,
            shortage_units_before=sol.baseline_cost.shortage_units,
            shortage_units_after=sol.cost.shortage_units,
            overflow_units_before=sol.baseline_cost.overflow_units,
            overflow_units_after=sol.cost.overflow_units,
            shortage_reduction=sol.shortage_reduction,
            overflow_reduction=sol.overflow_reduction,
            total_cost=sol.cost.total_cost,
            baseline_cost=sol.baseline_cost.total_cost,
            moves=[
                MoveOut(
                    origin_station_id=m.origin_id,
                    destination_station_id=m.destination_id,
                    quantity=m.quantity,
                    distance_km=m.distance_km,
                )
                for m in sol.plan.moves
            ],
            stations=[
                StationStateOut(
                    station_id=s.station_id,
                    name=s.name,
                    zone_id=s.zone_id,
                    bikes_before=s.bikes_before,
                    bikes_after=s.bikes_after,
                    target=s.target,
                    base_target=s.base_target,
                    capacity=s.capacity,
                    shortage_before=s.shortage_before,
                    shortage_after=s.shortage_after,
                )
                for s in sol.stations
            ],
            note=note,
        )

    @app.post("/v1/recommendations/stations")
    def recommend_stations(body: RecommendationApiRequest) -> dict:
        """RENT/RETURN Top-3 with reason codes (V1_Prompt §15). Simulated demo model."""
        from .recommendations import DEMO_NOTE, RecsysUnavailable, recommend

        try:
            result, failures = recommend(body.mode, body.lat, body.lng, body.cutoff, body.is_member)
        except RecsysUnavailable as e:
            raise HTTPException(
                status_code=503,
                detail={"error_code": "recsys_unavailable", "message": str(e)},
            ) from e
        payload = result.model_dump(mode="json")
        payload["note"] = DEMO_NOTE
        payload["failures"] = [f.__dict__ for f in failures]
        return payload

    @app.get("/v1/experiments/switchback")
    def experiments_switchback() -> dict:
        """SIMULATED clustered-switchback battery results for the Experiment Lab (§17, §18)."""
        from .experiments import run_battery

        return run_battery()

    @app.get("/v1/anomalies")
    def anomalies_endpoint() -> dict:
        """Anomaly Center: 4 detector families over the synthetic-fault scenario (§12)."""
        from .anomaly import anomalies

        return anomalies()

    @app.post("/v2/news/sync")
    def news_sync_endpoint(body: NewsSyncRequest | None = None) -> dict:
        """V2: on-demand LIVE news pull from GDELT (free, no key). Degrades gracefully offline."""
        from .news_sync import sync_live_news

        req = body or NewsSyncRequest()
        return sync_live_news(
            req.query, timespan_hours=req.timespan_hours, max_records=req.max_records
        )

    @app.get("/v1/news/search")
    def news_search(q: str, k: int = 5) -> dict:
        """Semantic search over the accumulating news vector store (FAISS)."""
        from .news import NewsSearchUnavailable, search

        try:
            return search(q, k=k)
        except NewsSearchUnavailable as e:
            raise HTTPException(
                status_code=503,
                detail={"error_code": "vectorstore_unavailable", "message": str(e)},
            ) from e

    @app.get("/v1/news/clusters")
    def news_clusters(threshold: float = 0.3) -> dict:
        """Same-event clusters over the news vector store."""
        from .news import NewsSearchUnavailable, clusters

        try:
            return clusters(threshold=threshold)
        except NewsSearchUnavailable as e:
            raise HTTPException(
                status_code=503,
                detail={"error_code": "vectorstore_unavailable", "message": str(e)},
            ) from e

    @app.get("/v2/rider/stations/search")
    def rider_station_search(engine: EngineDep, q: str = "", k: int = 20) -> dict:
        """V2 rider station search (offline). Empty ``q`` returns all stations by availability."""
        from .v2 import station_search

        return station_search(engine, q, engine.cutoff, limit=k)

    @app.get("/v2/rider/search/hybrid")
    def rider_hybrid_search(
        engine: EngineDep,
        q: str = "",
        lat: float | None = None,
        lng: float | None = None,
        k: int = 10,
    ) -> dict:
        """V2-03 hybrid geo-semantic search (BM25 + vector + geo, RRF); degrades to local."""
        from .v2 import hybrid_search

        return hybrid_search(engine, q, engine.cutoff, lat=lat, lng=lng, k=k)

    @app.post("/v2/rider/ask")
    def rider_ask_endpoint(engine: EngineDep, body: RiderAskRequest) -> dict:
        """V2 rider copilot: deterministic, tool-grounded answers to a natural-language query."""
        from .v2 import rider_ask

        return rider_ask(engine, body.query, engine.cutoff)

    @app.post("/v2/rider/plan-trip")
    def plan_trip_endpoint(engine: EngineDep, body: TripPlanRequest) -> dict:
        """V2-07 rider trip planner: walk → rent → bike → return → walk. Origin/destination come
        either as explicit place ids or parsed from a free-text query; all distances/times/stations
        are deterministic (never LLM). answer_mode marks how the query was parsed (rule_based here)."""
        from .trip_planner import plan_trip, resolve_endpoints
        from .v2 import _alias_index

        origin, destination = body.origin, body.destination
        answer_mode = "explicit"
        if not (origin and destination) and body.query:
            origin, destination = resolve_endpoints(body.query, _alias_index())
            answer_mode = "rule_based"  # LLM parser slots in here when a key is configured
        if not origin or not destination:
            return {"feasible": False, "reason": "unresolved_endpoints", "answer_mode": answer_mode,
                    "answer": "출발지와 목적지를 모두 알려주세요. 예: '시청에서 뉴포트 가고 싶어'."}
        return {**plan_trip(engine, engine.cutoff, origin, destination), "answer_mode": answer_mode}

    @app.post("/v2/pricing/quote")
    def pricing_quote_endpoint(engine: EngineDep, body: PricingQuoteRequest) -> dict:
        """V2-05 dynamic fare: SIMULATED SHADOW quotes + guardrails (never applied to a rider)."""
        from .v2 import pricing_quotes

        return pricing_quotes(engine, engine.cutoff, stale=body.stale, safety=body.safety)

    @app.post("/v2/pricing/revenue")
    def pricing_revenue_endpoint(engine: EngineDep, body: RevenueRequest) -> dict:
        """V2-05: event toggle → demand → pricing → revenue on one call (SIMULATED SHADOW)."""
        from .v2 import revenue_projection

        cutoff = body.cutoff or engine.cutoff
        return revenue_projection(
            engine, cutoff, tuple(body.disabled_event_ids), elasticity=body.elasticity
        )

    @app.post("/v2/operator/stations/import")
    def stations_import_endpoint(limit: int = 60) -> dict:
        """V2: preview a live import of the real Citi Bike station network (GBFS, free, no key)."""
        from .v2 import import_live_stations

        return import_live_stations(limit=limit)

    @app.post("/v2/operator/ask")
    def ops_ask_endpoint(engine: EngineDep, body: OpsAskRequest) -> dict:
        """V2-08 ops copilot: GraphRAG (LLM over the as-of event graph) when a key is configured,
        else the deterministic rule-based answer. Response carries ``answer_mode``.
        """
        from .v2 import ops_copilot_answer

        return ops_copilot_answer(engine, body.query, engine.cutoff)

    @app.get("/v2/operator/statistics")
    def operator_statistics_endpoint(engine: EngineDep) -> dict:
        """V2 operator analytics: real aggregate statistics of the as-of replay state."""
        from .v2 import operator_statistics

        return operator_statistics(engine, engine.cutoff)

    @app.get("/v2/operator/timeline")
    def operator_timeline_endpoint(engine: EngineDep) -> dict:
        """V2 operator analytics: as-of aggregates across the replay window (event-window view)."""
        from .v2 import operator_timeline

        return operator_timeline(engine)

    @app.get("/v2/cockpit/metrics")
    def cockpit_metrics_endpoint(mode: str = "historical_replay") -> dict:
        """V2-07: every headline cockpit metric, each resolved live from a committed reports/v2/**
        artifact and wrapped in the result envelope (run_id/artifact_id/claim_status/freshness).
        No hard-coded numbers; a missing artifact surfaces as a blocked envelope, never a fake value.
        """
        from contracts.enums import OperatingMode

        from .v2_metrics import cockpit_metrics

        return {"mode": mode, "metrics": cockpit_metrics(OperatingMode(mode))}

    @app.post(
        "/v2/operator/rebalancing/allocate",
        responses={400: {"model": ErrorResponse}},
    )
    def allocate_extra_bikes_endpoint(engine: EngineDep, body: ExtraBikeAllocationRequest) -> dict:
        """V2: optimally distribute operator-supplied extra bikes over the as-of network."""
        from .v2 import allocate_extra_bikes

        cutoff = body.cutoff or engine.cutoff
        start, end = DEMO_WINDOW
        if not (start <= cutoff <= end):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "cutoff_out_of_window",
                    "message": f"cutoff must be within [{start.isoformat()}, {end.isoformat()}]",
                },
            )
        return allocate_extra_bikes(engine, cutoff, body.extra_bikes)

    @app.get("/v2/model/predictive-lift")
    def predictive_lift_endpoint() -> dict:
        """V2-02 predictive-lift verdict on the demo fixture (honestly blocked_data, offline)."""
        from ml.forecasting.predictive_lift_demo import run

        return run()

    @app.get("/v1/model/lift")
    def model_lift() -> dict:
        """Measured M0/M1 ablation + event-lift verdict for the Model Lift Lab (§9, §10)."""
        from ml.forecasting.event_lift import event_lift_gate
        from ml.forecasting.registry import RegistryUnavailable, event_lift_summary

        try:
            summary = event_lift_summary()
            summary["gate"] = event_lift_gate()  # V1-04 claim gate
            return summary
        except RegistryUnavailable as e:
            raise HTTPException(
                status_code=503,
                detail={"error_code": "results_unavailable", "message": str(e)},
            ) from e

    @app.post("/v1/recommendations/compare-event-impact")
    def compare_event_impact_endpoint(body: RecommendationApiRequest) -> dict:
        """Event ON/OFF Top-3 overlap over a frozen candidate set (V1_Prompt §15)."""
        from .recommendations import DEMO_NOTE, RecsysUnavailable, compare_event_impact

        try:
            out = compare_event_impact(body.mode, body.lat, body.lng, body.cutoff)
        except RecsysUnavailable as e:
            raise HTTPException(
                status_code=503,
                detail={"error_code": "recsys_unavailable", "message": str(e)},
            ) from e
        out["note"] = DEMO_NOTE
        return out

    return app


app = create_app()

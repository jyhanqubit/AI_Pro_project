"""The five copilot tools as pure functions of (engine, arguments).

Both transports call these: the MCP server exposes them over stdio / streamable HTTP, and the
in-process transport calls them directly. Keeping one implementation guarantees the two paths
return byte-identical payloads, which is what the before/after benchmark relies on.

Nothing here computes a new number. Each function delegates to the existing API / copilot
functions (``graphrag`` context assembly, ``operator_statistics``, ``pricing_quotes``, the typed
metric tools, ``model_forecast``) and adds the provenance block. ``cutoff`` is always an explicit
argument: the tools hold no replay state, so they behave identically in any process.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from contracts.v2.enums import ClaimStatus
from contracts.v2.envelope import ResultEnvelope
from contracts.v2.mcp import (
    GraphContext,
    GraphContextCard,
    ModelForecastResult,
    OperatorStatisticsResult,
    PricingQuotesResult,
    PricingRules,
    ToolErrorPayload,
)


class ToolFailure(Exception):
    """A tool failed in an anticipated way; carries the structured API-style error payload."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.payload = ToolErrorPayload(error_code=error_code, message=message)


def _now() -> datetime:
    return datetime.now(UTC)


def check_cutoff(cutoff: datetime) -> datetime:
    """Same window rule as the HTTP API (400 cutoff_out_of_window)."""
    from services.api.replay import DEMO_WINDOW

    start, end = DEMO_WINDOW
    if cutoff.tzinfo is None:
        raise ToolFailure("cutoff_naive", "cutoff must be timezone-aware")
    if not (start <= cutoff <= end):
        raise ToolFailure(
            "cutoff_out_of_window",
            f"cutoff must be within [{start.isoformat()}, {end.isoformat()}]",
        )
    return cutoff


def graph_context(engine: Any, cutoff: datetime, max_events: int = 12) -> GraphContext:
    from services.api.graphrag import _graph_context_cards

    cutoff = check_cutoff(cutoff)
    events, n = _graph_context_cards(engine, cutoff, max_events=max_events)
    return GraphContext(
        tool="get_graph_context",
        mode=engine.mode,
        cutoff=cutoff,
        claim_status=ClaimStatus.DEMO_FIXTURE,
        freshness=_now(),
        event_count=n,
        events=[GraphContextCard(**c) for c in events],
    )


def operator_statistics(engine: Any, cutoff: datetime) -> OperatorStatisticsResult:
    from services.api.v2 import operator_statistics as _stats

    cutoff = check_cutoff(cutoff)
    return OperatorStatisticsResult(
        tool="get_operator_statistics",
        mode=engine.mode,
        cutoff=cutoff,
        claim_status=ClaimStatus.DEMO_FIXTURE,
        freshness=_now(),
        statistics=_stats(engine, cutoff),
    )


def metric(engine: Any, name: str) -> ResultEnvelope[Any]:
    from ml.copilot.tools import REGISTRY, ToolUnavailable
    from services.api.v2_metrics import _artifact_meta

    fn = REGISTRY.get(name)
    if fn is None:
        raise ToolFailure("unknown_metric", f"no typed tool named {name!r}")
    try:
        res = fn()
    except ToolUnavailable as exc:
        raise ToolFailure("tool_unavailable", str(exc)) from exc
    run_id, freshness = _artifact_meta(res.artifact_id)
    return ResultEnvelope(
        value=res.value,
        run_id=run_id,
        artifact_id=res.artifact_id,
        mode=engine.mode,
        claim_status=ClaimStatus(res.claim_status),
        freshness=freshness or "1970-01-01T00:00:00+00:00",
    )


def model_forecast(engine: Any, top: int = 20) -> ModelForecastResult:
    from services.api.model_serving import ServingUnavailable
    from services.api.model_serving import model_forecast as _forecast

    try:
        payload = _forecast(top=top)
    except ServingUnavailable as exc:
        raise ToolFailure("promoted_model_unavailable", str(exc)) from exc
    return ModelForecastResult(
        tool="get_model_forecast",
        mode=engine.mode,
        cutoff=None,
        claim_status=ClaimStatus(payload["claim_status"]),
        freshness=payload["freshness"],
        run_id=payload["run_id"],
        artifact_id="reports/v2/holdout/promoted_model.json",
        forecast=payload,
    )


def pricing_quotes(
    engine: Any,
    cutoff: datetime,
    *,
    stale: bool = False,
    safety: bool = False,
    rules: PricingRules | None = None,
) -> PricingQuotesResult:
    from services.api.v2 import pricing_quotes as _quotes

    cutoff = check_cutoff(cutoff)
    cfg = rules.to_config() if rules is not None else None
    payload = _quotes(engine, cutoff, stale=stale, safety=safety, cfg=cfg)
    return PricingQuotesResult(
        tool="get_pricing_quotes",
        mode=engine.mode,
        cutoff=cutoff,
        claim_status=ClaimStatus.SIMULATED,
        freshness=_now(),
        pricing=payload,
        operator_override=rules is not None,
        rules_applied=rules,
    )

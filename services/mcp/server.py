"""ShockFlow operator-copilot MCP server (official ``mcp`` Python SDK, ``MCPServer``).

Exposes the five copilot tools over the Model Context Protocol so any MCP client — the GraphRAG
copilot in this repo, an IDE, another agent — can ground numbers in the same artifacts and as-of
replay state the dashboards use. Tool bodies live in :mod:`services.mcp.core` and are shared with
the in-process transport; this module only adds the protocol surface.

Run:
    python -m services.mcp.server                   # stdio (default; what the API spawns)
    python -m services.mcp.server --transport streamable-http   # a separate service

Errors are raised as ``ToolError`` whose message is the JSON ``{error_code, message}`` payload,
so a client can recover the same structured error the HTTP API returns.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from contracts.v2.envelope import ResultEnvelope
from contracts.v2.mcp import (
    GraphContext,
    MetricName,
    ModelForecastResult,
    OperatorStatisticsResult,
    PricingQuotesResult,
    PricingRules,
)
from services.mcp import core

server = MCPServer(
    name="shockflow-ops",
    version="0.1.0",
    instructions=(
        "Operator copilot tools for ShockFlow AI (NYC bike-share demand forecasting). Every result "
        "carries mode / cutoff / claim_status / freshness; numbers cite run_id and artifact_id. "
        "Pass an explicit timezone-aware cutoff — the tools hold no replay state."
    ),
    log_level="WARNING",
)


def _engine() -> Any:
    from services.api.replay import get_engine

    return get_engine()


def _guard(fn, *args: Any, **kwargs: Any):
    try:
        return fn(*args, **kwargs)
    except core.ToolFailure as exc:
        raise ToolError(exc.payload.model_dump_json()) from exc
    except ValidationError as exc:
        raise ToolError(
            json.dumps({"error_code": "validation_error", "message": str(exc)})
        ) from exc


@server.tool(structured_output=True)
def get_graph_context(cutoff: datetime, max_events: int = 12) -> GraphContext:
    """As-of event graph context for GraphRAG: events available at `cutoff`, their grounded
    evidence, the zones they reach and each zone's model-attributed forecast delta."""
    return _guard(core.graph_context, _engine(), cutoff, max_events)


@server.tool(structured_output=True)
def get_operator_statistics(cutoff: datetime) -> OperatorStatisticsResult:
    """As-of aggregate operations state (utilization, shortage, event mix, surge zones) — the
    same payload as GET /v2/operator/statistics."""
    return _guard(core.operator_statistics, _engine(), cutoff)


@server.tool(structured_output=True)
def get_metric(name: MetricName) -> ResultEnvelope[Any]:
    """A measured/simulated headline number read from its committed artifact (WAPE, profit lift,
    MPC regret, best policy, guardrail violations, LLM news value, served model), enveloped with
    run_id / artifact_id / claim_status / freshness."""
    return _guard(core.metric, _engine(), name)


@server.tool(structured_output=True)
def get_model_forecast(top: int = 20) -> ModelForecastResult:
    """Next-hour departures per H3 zone from the promoted measured model (runs predict now) —
    the same payload as GET /v2/model/forecast."""
    return _guard(core.model_forecast, _engine(), top)


@server.tool(structured_output=True)
def get_pricing_quotes(
    cutoff: datetime,
    stale: bool = False,
    safety: bool = False,
    rules: PricingRules | None = None,
) -> PricingQuotesResult:
    """SIMULATED SHADOW fare quotes as-of `cutoff`. `rules` lets an operator override the pricing
    rule knobs (base fare, multiplier cap, tier thresholds, credit, event normaliser) within the
    system guardrails; the response echoes the rules applied."""
    return _guard(core.pricing_quotes, _engine(), cutoff, stale=stale, safety=safety, rules=rules)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="services.mcp.server", description=__doc__)
    ap.add_argument(
        "--transport",
        choices=("stdio", "streamable-http", "sse"),
        default="stdio",
    )
    args = ap.parse_args(argv)
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()

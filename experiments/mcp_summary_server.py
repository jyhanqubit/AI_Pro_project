"""An *additional* MCP server exposing the summary tools (the existing five tools are untouched).

Run: python -m experiments.mcp_summary_server            # stdio

Each tool calls the same ``services.mcp.core`` function the full tool calls, then applies the
summariser from :mod:`experiments.mcp_summary`, so the numbers are the served numbers; only the
shape is reduced. ``full_result_ref`` in every result says how to fetch the full payload.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

from mcp.server.mcpserver import MCPServer

from experiments.mcp_summary import (
    summarize_graph_context,
    summarize_model_forecast,
    summarize_operator_statistics,
)
from services.api.copilot_tools import InProcessTools

server = MCPServer(
    name="shockflow-ops-summary",
    version="0.1.0",
    instructions=(
        "Compact variants of the ShockFlow operator tools: provenance + aggregates + top-N rows. "
        "Every result carries full_result_ref (tool, args, run_id, artifact_id) for the full payload."
    ),
    log_level="WARNING",
)


def _tools() -> InProcessTools:
    from services.api.replay import get_engine

    return InProcessTools(get_engine())


@server.tool(structured_output=True)
def get_model_forecast_summary(
    zone_ids: list[str] | None = None, top_n: int = 5, top: int = 20
) -> dict[str, Any]:
    """Next-hour departures from the promoted model for the asked zones only (or the top_n rows),
    with the aggregate over all served zones and a reference to the full get_model_forecast result."""
    return summarize_model_forecast(_tools().model_forecast(top), zone_ids=zone_ids, top_n=top_n)


@server.tool(structured_output=True)
def get_graph_context_summary(
    cutoff: datetime, max_events: int = 12, top_zones: int = 3
) -> dict[str, Any]:
    """Events available as-of `cutoff` with their evidence sentence and the top_zones largest
    forecast-delta zones per event (zone count kept); reference to the full get_graph_context."""
    return summarize_graph_context(_tools().graph_context(cutoff, max_events), top_zones=top_zones)


@server.tool(structured_output=True)
def get_operator_statistics_summary(cutoff: datetime, top_n: int = 3) -> dict[str, Any]:
    """As-of operations aggregates (utilization, shortage, event mix) plus the top_n surge and
    shortage zones; the per-zone table is omitted and referenced via full_result_ref."""
    return summarize_operator_statistics(_tools().operator_statistics(cutoff), top_n=top_n)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="experiments.mcp_summary_server", description=__doc__)
    ap.add_argument("--transport", choices=("stdio", "streamable-http", "sse"), default="stdio")
    args = ap.parse_args(argv)
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()

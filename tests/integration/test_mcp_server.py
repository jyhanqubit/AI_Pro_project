"""MCP server for the operator copilot tools. CLAUDE.md §12, §22; V2 addendum (LLM boundaries).

Spawns the real server over stdio and checks the transport contract: the five tools are listed,
every result carries provenance, payloads are identical to the in-process transport (the
before/after benchmark relies on this), errors keep the API's ``error_code`` shape, the operator
pricing override is honoured but cannot exceed the system guardrail, and a broken transport
degrades to in-process instead of failing the copilot.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from contracts.v2.mcp import TOOL_NAMES, PricingRules
from services.api import copilot_tools
from services.api.copilot_tools import InProcessTools, McpStdioTools, ToolCallError
from services.api.replay import DEMO_WINDOW, get_engine

PROVENANCE = ("mode", "claim_status", "freshness")


@pytest.fixture(scope="module")
def mcp():
    client = McpStdioTools(timeout_s=60)
    client.start()
    yield client
    client.close()


@pytest.fixture
def engine():
    e = get_engine()
    _, end = DEMO_WINDOW
    e.set_cutoff(end)
    return e


def _strip(d: dict) -> str:
    d = dict(d)
    d.pop("freshness", None)
    return json.dumps(d, sort_keys=True)


def test_lists_exactly_the_five_tools(mcp) -> None:
    import asyncio

    listed = asyncio.run_coroutine_threadsafe(mcp._session.list_tools(), mcp._loop).result(30)
    names = {t.name for t in listed.tools}
    assert names == set(TOOL_NAMES)
    # every tool publishes an output schema (structured content), not just free text
    assert all(t.output_schema for t in listed.tools)


def test_payloads_match_in_process_transport(mcp, engine) -> None:
    cutoff = engine.cutoff
    local = InProcessTools(engine)
    assert _strip(local.graph_context(cutoff)) == _strip(mcp.graph_context(cutoff))
    assert _strip(local.operator_statistics(cutoff)) == _strip(mcp.operator_statistics(cutoff))
    assert _strip(local.metric("forecast_wape")) == _strip(mcp.metric("forecast_wape"))
    assert _strip(local.pricing_quotes(cutoff)) == _strip(mcp.pricing_quotes(cutoff))


def test_every_result_carries_provenance(mcp, engine) -> None:
    cutoff = engine.cutoff
    for payload in (
        mcp.graph_context(cutoff),
        mcp.operator_statistics(cutoff),
        mcp.pricing_quotes(cutoff),
    ):
        assert all(k in payload for k in PROVENANCE)
        assert payload["cutoff"] == cutoff.isoformat()
    metric = mcp.metric("forecast_wape")
    assert metric["run_id"].startswith("run_")
    assert metric["artifact_id"].startswith("reports/v2/")
    assert metric["claim_status"] == "measured"
    assert metric["value"] == pytest.approx(0.4974, abs=1e-4)


def test_graph_context_is_grounded(mcp, engine) -> None:
    ctx = mcp.graph_context(engine.cutoff)
    real = {e.event_id for e in engine.available_events(engine.cutoff)}
    assert ctx["events"]
    assert all(c["event_id"] in real and c["evidence"] for c in ctx["events"])


def test_cutoff_is_explicit_not_process_state(mcp, engine) -> None:
    # The server process never saw this engine's set_cutoff; it must answer for the cutoff sent.
    start, end = DEMO_WINDOW
    early = mcp.graph_context(start)
    late = mcp.graph_context(end)
    assert early["event_count"] == 0
    assert late["event_count"] > 0
    assert early["cutoff"] == start.isoformat() and late["cutoff"] == end.isoformat()


def test_errors_keep_api_error_codes(mcp) -> None:
    with pytest.raises(ToolCallError) as exc:
        mcp.graph_context(datetime(2026, 7, 12, 23, 0, tzinfo=UTC))
    assert exc.value.error_code == "cutoff_out_of_window"
    with pytest.raises(ToolCallError) as exc:
        mcp.metric("not_a_metric")
    assert exc.value.error_code == "validation_error"


def test_operator_pricing_rules_apply_within_guardrail(mcp, engine) -> None:
    cutoff = engine.cutoff
    default = mcp.pricing_quotes(cutoff)
    capped = mcp.pricing_quotes(cutoff, rules=PricingRules(max_multiplier=1.25, base_fare=1.5))
    assert default["operator_override"] is False
    assert capped["operator_override"] is True
    assert capped["rules_applied"]["max_multiplier"] == 1.25
    assert capped["pricing"]["base_fare"] == 1.5
    assert max(q["tier_multiplier"] for q in capped["pricing"]["quotes"]) <= 1.25
    assert capped["pricing"]["pricing_config_version"].endswith("+operator")
    # The system guardrail is a hard cap: the contract itself refuses a higher multiplier.
    with pytest.raises(ValueError):
        PricingRules(max_multiplier=9.0)


def test_copilot_degrades_when_transport_is_broken(engine, monkeypatch) -> None:
    from services.api import v2

    broken = McpStdioTools(timeout_s=5, command=["/nonexistent/mcp-server"])
    monkeypatch.setattr(copilot_tools, "get_copilot_tools", lambda _e: broken)
    r = v2.ops_copilot_answer(engine, "지금 현황 어때?", engine.cutoff, tools=None)
    assert r["answer_mode"] == "rule_based"
    assert r["tool_transport"] in ("inprocess_fallback", "inprocess")
    assert r["answer"]


def test_copilot_answers_over_mcp(mcp, engine) -> None:
    from services.api import v2

    r = v2.ops_copilot_answer(engine, "지금 현황 어때?", engine.cutoff, tools=mcp)
    assert r["tool_transport"] == "mcp_stdio"
    assert r["answer_mode"] == "rule_based"  # no LLM key in tests
    local = v2.ops_copilot_answer(
        engine, "지금 현황 어때?", engine.cutoff, tools=InProcessTools(engine)
    )
    assert r["answer"] == local["answer"]

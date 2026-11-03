"""Experiment 1 (experiments/mcp_tokens, experiments/mcp_summary): reproducibility and answer safety.

Offline: the fixture replay engine and the in-process transport. The summaries must carry the
answer to each scenario question (the check_* functions assert it) and the same payload must
count to the same number of tokens; the staged layouts must never cost more than all five tools.
The tiktoken encoding file is fetched from the network on first use, so the token tests skip —
with a reason — where it is not cached (CI has no egress); the summary tests always run.
"""

from __future__ import annotations

import asyncio

import pytest

from experiments import mcp_summary as ms
from services.api.copilot_tools import InProcessTools
from services.api.replay import DEMO_WINDOW, get_engine


@pytest.fixture(scope="module")
def tools():
    e = get_engine()
    _, end = DEMO_WINDOW
    e.set_cutoff(end)
    return InProcessTools(e), end


def test_forecast_summary_keeps_the_asked_zone_and_provenance(tools) -> None:
    t, _ = tools
    raw = t.model_forecast(20)
    zone = raw["forecast"]["forecasts"][3]["zone_id"]
    summ = ms.summarize_model_forecast(raw, zone_ids=[zone])
    assert [r["zone_id"] for r in summ["rows"]] == [zone]
    assert summ["rows_in_full"] == 20 and summ["full_result_ref"]["tool"] == "get_model_forecast"
    assert "lat" not in summ["rows"][0]  # only the fields the question needs
    ms.check_model_forecast(raw, summ, zone)
    with pytest.raises(StopIteration):  # a zone the summary does not carry is not silently answered
        ms.check_model_forecast(raw, summ, raw["forecast"]["forecasts"][0]["zone_id"])


def test_graph_summary_keeps_ids_evidence_and_top_zone(tools) -> None:
    t, cutoff = tools
    raw = t.graph_context(cutoff, 12)
    summ = ms.summarize_graph_context(raw, top_zones=1)
    assert summ["event_count"] == raw["event_count"] and len(summ["events"]) == len(raw["events"])
    assert all(len(e["top_zones"]) == 1 and e["zone_count"] >= 1 for e in summ["events"])
    ms.check_graph_context(raw, summ)


def test_operator_summary_keeps_aggregates_and_drops_the_zone_table(tools) -> None:
    t, cutoff = tools
    raw = t.operator_statistics(cutoff)
    summ = ms.summarize_operator_statistics(raw, top_n=3)
    assert "zones" not in summ and summ["zones_in_full"] == len(raw["statistics"]["zones"])
    assert len(summ["top_surge_zones"]) == 3 and len(summ["top_shortage_zones"]) == 3
    ms.check_operator_statistics(raw, summ)


def test_summary_server_lists_only_its_three_tools() -> None:
    from experiments.mcp_summary_server import server

    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {
        "get_model_forecast_summary",
        "get_graph_context_summary",
        "get_operator_statistics_summary",
    }


def _encoding_or_skip():
    tiktoken = pytest.importorskip("tiktoken")
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception as exc:  # noqa: BLE001 — environment-specific: encoding file not cached
        pytest.skip(f"cl100k_base encoding not available offline: {exc!r}")


def test_token_counts_are_reproducible_and_staged_never_costs_more(tools) -> None:
    from experiments import mcp_tokens as mt

    enc = _encoding_or_skip()
    t, cutoff = tools
    raw = t.operator_statistics(cutoff)
    summ = ms.summarize_operator_statistics(raw)
    assert mt.count_tokens(raw, enc) == mt.count_tokens(raw, enc)
    assert mt.count_tokens(summ, enc) < mt.count_tokens(raw, enc)
    # freshness is normalised, so a payload that differs only there counts the same
    other = {**raw, "freshness": "1999-12-31T23:59:59.000001+00:00"}
    assert mt.count_tokens(other, enc) == mt.count_tokens(raw, enc)

    defs = mt.tool_definitions()
    staged = mt.staged_exposure(defs, enc)
    assert staged["catalog_tokens"] < staged["all_five_tokens"]
    for row in staged["scenarios"]:
        assert row["needed_only_tokens"] < row["two_stage_tokens"] <= row["all_five_tokens"]

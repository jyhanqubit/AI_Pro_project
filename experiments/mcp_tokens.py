"""Experiment 1 — MCP tool-definition and response token accounting, full vs summary vs staged.

What is measured (all with ``tiktoken`` ``cl100k_base``, an *approximation* of the tokenizer any
particular LLM provider actually uses; the relative comparison is the point, not the absolute):

1. tool definitions: what an MCP client puts in the model prompt for each of the five tools
   (``name``, ``description``, ``input_schema``), serialised as compact UTF-8 JSON; and the same
   with ``output_schema`` included, for clients that forward structured-output schemas;
2. per scenario: the raw payload the real server returns over **stdio** (``McpStdioTools``) and
   the summary payload (:mod:`experiments.mcp_summary`), plus the answer-preservation check;
3. staged exposure: tokens of the five definitions vs only the tool(s) a scenario needs vs a
   two-stage "catalog (name + first sentence) then the one selected tool" layout.

Determinism: the cutoff is the fixed end of the demo window; ``freshness`` is replaced by a
constant of the same shape before counting (it is the only field whose text changes per call).

Usage: python -m experiments.mcp_tokens [--out reports/agent_experiments/mcp_tokens.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from experiments.mcp_summary import (
    check_graph_context,
    check_model_forecast,
    check_operator_statistics,
    summarize_graph_context,
    summarize_model_forecast,
    summarize_operator_statistics,
)

OUT_DEFAULT = Path("reports/agent_experiments/mcp_tokens.json")
ENCODING = "cl100k_base"
FRESHNESS_CONST = "2026-01-01T00:00:00+00:00"
SEED = 42  # no randomness is used; recorded so every experiment reports one


def _enc():
    import tiktoken

    return tiktoken.get_encoding(ENCODING)


def _normalise(obj: Any) -> Any:
    """Replace every ``freshness`` value with a constant so counts are reproducible run to run."""
    if isinstance(obj, dict):
        return {
            k: (FRESHNESS_CONST if k == "freshness" and v is not None else _normalise(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_normalise(v) for v in obj]
    return obj


def to_text(obj: Any) -> str:
    """Compact UTF-8 JSON — the cheapest faithful serialisation a client would send."""
    return json.dumps(_normalise(obj), ensure_ascii=False, separators=(",", ":"), default=str)


def count_tokens(obj: Any, enc=None) -> int:
    enc = enc or _enc()
    return len(enc.encode(to_text(obj), disallowed_special=()))


# --- tool definitions ---------------------------------------------------------------------------


def tool_definitions() -> list[dict[str, Any]]:
    """The five tools as the server lists them (name, description, inputSchema, outputSchema)."""
    from services.mcp.server import server

    tools = asyncio.run(server.list_tools())
    return [t.model_dump(by_alias=True, exclude_none=True) for t in tools]


def client_view(tool: dict[str, Any], *, with_output_schema: bool = False) -> dict[str, Any]:
    """What a chat-completions / Messages client forwards to the model for one tool."""
    d = {
        "name": tool["name"],
        "description": tool.get("description", ""),
        "input_schema": tool["inputSchema"],
    }
    if with_output_schema and tool.get("outputSchema"):
        d["output_schema"] = tool["outputSchema"]
    return d


def catalog_entry(tool: dict[str, Any]) -> dict[str, str]:
    """Stage-1 catalog line: name + first sentence of the description, no schema."""
    desc = " ".join(tool.get("description", "").split())
    first = desc.split(". ")[0].rstrip(".") + "." if desc else ""
    return {"name": tool["name"], "description": first}


# --- scenarios ----------------------------------------------------------------------------------

SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "id": "A_zone_forecast",
        "question": "zone 892a107216bffff 의 다음 1시간 예측 출발 수는? (모델, 서빙 시각 포함)",
        "tools_needed": ["get_model_forecast"],
    },
    {
        "id": "B_event_evidence",
        "question": "cutoff 시점에 사용 가능한 이벤트는 무엇이고 각각의 근거 문장과 가장 큰 영향 zone 은?",
        "tools_needed": ["get_graph_context"],
    },
    {
        "id": "C_ops_shortage_surge",
        "question": "지금 부족 정류장 수와 부족 대수, 시스템 이용률, 가장 급등하는 zone 은? (재배치가 다루는 상태)",
        "tools_needed": ["get_operator_statistics"],
    },
    {
        "id": "D_rebalancing_policy_metric",
        "question": "(보조) 측정된 최적 재배치 정책과 그 비용은?",
        "tools_needed": ["get_metric"],
    },
)
ZONE_A = "892a107216bffff"


def run_scenarios(tools: Any, cutoff: datetime) -> list[dict[str, Any]]:
    """Call the real server for each scenario, build the summary, and check the answer survives."""
    enc = _enc()
    out: list[dict[str, Any]] = []

    raw = tools.model_forecast(20)
    summ = summarize_model_forecast(raw, zone_ids=[ZONE_A])
    out.append(_row(SCENARIOS[0], raw, summ, check_model_forecast(raw, summ, ZONE_A), enc))

    raw = tools.graph_context(cutoff, 12)
    summ = summarize_graph_context(
        raw, top_zones=1
    )  # the question asks for the largest-delta zone only
    out.append(_row(SCENARIOS[1], raw, summ, check_graph_context(raw, summ), enc))

    raw = tools.operator_statistics(cutoff)
    summ = summarize_operator_statistics(raw, top_n=3)
    out.append(_row(SCENARIOS[2], raw, summ, check_operator_statistics(raw, summ), enc))

    raw = tools.metric("best_rebalancing_policy")
    out.append(
        _row(
            SCENARIOS[3],
            raw,
            raw,
            "already compact (one enveloped number); no summary variant — summary == raw",
            enc,
        )
    )
    return out


def _row(sc: dict[str, Any], raw: Any, summ: Any, check: str, enc) -> dict[str, Any]:
    t_raw, t_sum = count_tokens(raw, enc), count_tokens(summ, enc)
    return {
        **sc,
        "raw_tokens": t_raw,
        "summary_tokens": t_sum,
        "reduction_pct": round(100.0 * (1 - t_sum / t_raw), 1) if t_raw else None,
        "raw_chars": len(to_text(raw)),
        "summary_chars": len(to_text(summ)),
        "answer_preserved": check,
        "raw_payload": _normalise(raw),
        "summary_payload": _normalise(summ),
    }


# --- staged exposure ----------------------------------------------------------------------------


def staged_exposure(defs: list[dict[str, Any]], enc) -> dict[str, Any]:
    full = [client_view(t) for t in defs]
    full_tokens = count_tokens(full, enc)
    catalog = [catalog_entry(t) for t in defs]
    catalog_tokens = count_tokens(catalog, enc)
    per_tool = {t["name"]: count_tokens(client_view(t), enc) for t in defs}
    rows = []
    for sc in SCENARIOS:
        needed = [client_view(t) for t in defs if t["name"] in sc["tools_needed"]]
        needed_tokens = count_tokens(needed, enc)
        two_stage = catalog_tokens + needed_tokens
        rows.append(
            {
                "id": sc["id"],
                "tools_needed": sc["tools_needed"],
                "all_five_tokens": full_tokens,
                "needed_only_tokens": needed_tokens,
                "needed_only_reduction_pct": round(100.0 * (1 - needed_tokens / full_tokens), 1),
                "two_stage_tokens": two_stage,
                "two_stage_reduction_pct": round(100.0 * (1 - two_stage / full_tokens), 1),
            }
        )
    return {
        "all_five_tokens": full_tokens,
        "catalog_tokens": catalog_tokens,
        "per_tool_tokens": per_tool,
        "scenarios": rows,
    }


# --- main -----------------------------------------------------------------------------------------


def _git_commit() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout.strip()
        return sha + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv: list[str] | None = None) -> dict[str, Any]:
    ap = argparse.ArgumentParser(prog="experiments.mcp_tokens", description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument(
        "--in-process", action="store_true", help="use the in-process transport instead of stdio"
    )
    ns = ap.parse_args(argv)

    from services.api.copilot_tools import InProcessTools, McpStdioTools
    from services.api.replay import DEMO_WINDOW, get_engine

    _, cutoff = DEMO_WINDOW
    engine = get_engine()
    engine.set_cutoff(cutoff)
    enc = _enc()

    defs = tool_definitions()
    definitions = [
        {
            "name": t["name"],
            "tokens_name_desc_input": count_tokens(client_view(t), enc),
            "tokens_with_output_schema": count_tokens(client_view(t, with_output_schema=True), enc),
            "input_schema_properties": sorted(t["inputSchema"].get("properties", {})),
        }
        for t in defs
    ]

    if ns.in_process:
        tools: Any = InProcessTools(engine)
        transport = "in_process"
    else:
        tools = McpStdioTools(timeout_s=60)
        tools.start()
        transport = "mcp_stdio"
    try:
        scenarios = run_scenarios(tools, cutoff)
    finally:
        if transport == "mcp_stdio":
            tools.close()

    summary_defs = _summary_tool_definitions(enc)

    result = {
        "experiment": "mcp_tokens",
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(),
        "command": "python -m experiments.mcp_tokens" + (" --in-process" if ns.in_process else ""),
        "seed": SEED,
        "tokenizer": {
            "library": "tiktoken",
            "encoding": ENCODING,
            "note": "approximation; provider tokenizers differ. Counts are over compact UTF-8 JSON "
            "(ensure_ascii=False, no spaces) with `freshness` normalised to a constant.",
        },
        "transport": transport,
        "cutoff": cutoff.isoformat(),
        "mode": engine.mode,
        "tool_definitions": {
            "all_five_tokens_name_desc_input": count_tokens([client_view(t) for t in defs], enc),
            "all_five_tokens_with_output_schema": count_tokens(
                [client_view(t, with_output_schema=True) for t in defs], enc
            ),
            "per_tool": definitions,
            "summary_server_tools": summary_defs,
        },
        "scenarios": scenarios,
        "staged_exposure": staged_exposure(defs, enc),
    }
    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    _print_table(result)
    print(f"\nwrote {ns.out}")
    return result


def _summary_tool_definitions(enc) -> dict[str, Any]:
    from experiments.mcp_summary_server import server as summary_server

    tools = asyncio.run(summary_server.list_tools())
    defs = [t.model_dump(by_alias=True, exclude_none=True) for t in tools]
    return {
        "all_tokens_name_desc_input": count_tokens([client_view(t) for t in defs], enc),
        "per_tool": {t["name"]: count_tokens(client_view(t), enc) for t in defs},
    }


def _print_table(res: dict[str, Any]) -> None:
    td = res["tool_definitions"]
    print(
        f"tool definitions (5 tools): {td['all_five_tokens_name_desc_input']} tokens "
        f"(+output schemas: {td['all_five_tokens_with_output_schema']})"
    )
    for t in td["per_tool"]:
        print(
            f"  {t['name']:26s} {t['tokens_name_desc_input']:5d}  (+out {t['tokens_with_output_schema']})"
        )
    print("\nscenario                      raw   summary  reduction")
    for s in res["scenarios"]:
        print(
            f"  {s['id']:28s} {s['raw_tokens']:5d}  {s['summary_tokens']:7d}  {s['reduction_pct']:6.1f}%  | {s['answer_preserved']}"
        )
    st = res["staged_exposure"]
    print(f"\nstaged exposure: all five {st['all_five_tokens']} | catalog {st['catalog_tokens']}")
    for r in st["scenarios"]:
        print(
            f"  {r['id']:28s} needed-only {r['needed_only_tokens']:4d} (-{r['needed_only_reduction_pct']}%)  "
            f"two-stage {r['two_stage_tokens']:4d} (-{r['two_stage_reduction_pct']}%)"
        )


if __name__ == "__main__":
    sys.exit(0 if main() else 1)

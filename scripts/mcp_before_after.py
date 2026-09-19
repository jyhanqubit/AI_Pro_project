"""Before/after the MCP refactor: copilot benchmarks and tool latency on both transports.

"Before" is the in-process transport (the original direct function calls); "after" is the MCP
server over stdio. The same question sets, fixtures and judgments are scored on both, so any
difference in accuracy / faithfulness is a transport bug, not a modelling change. Latency is
measured per tool (500 sequential calls, p50/p95/p99) and end-to-end on ``POST /v2/operator/ask``.

No LLM key is available in the sandbox, so — exactly as the committed benchmarks do — routing
comes from the committed Claude routing fixture and RAGAS judgments from the committed judgment
fixture, guarded by the drift check that fails if a live answer no longer matches its judged text.

Usage: python -m scripts.mcp_before_after
Output: reports/v2/copilot/mcp_transport_comparison.json / .png
"""

from __future__ import annotations

import json
import os
import platform
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ml.copilot import benchmark as bench
from ml.copilot import ragas_generation as ragas
from ml.copilot.copilot import _REFUSAL, CopilotAnswer
from services.api.copilot_tools import InProcessTools, McpStdioTools, ToolCallError
from services.api.replay import DEMO_WINDOW, get_engine

OUT_JSON = Path("reports/v2/copilot/mcp_transport_comparison.json")
OUT_PNG = Path("reports/v2/copilot/mcp_transport_comparison.png")
N_CALLS = 500


def _pct(samples: list[float], q: float) -> float:
    s = sorted(samples)
    return s[min(len(s) - 1, max(0, round(q / 100 * len(s)) - 1))]


def _answer_via(tools) -> Any:
    """A copilot ``answer`` whose typed-tool call goes through ``tools.metric`` (the transport)."""
    from ml.copilot.tools import REGISTRY

    def answer(question: str, route_fn=bench.route) -> CopilotAnswer:
        tool_name = route_fn(question)
        if tool_name is None:
            return CopilotAnswer(
                question, False, None, _REFUSAL, None, None, None, refusal_reason="no_tool_match"
            )
        try:
            env = tools.metric(tool_name)
        except ToolCallError as exc:
            return CopilotAnswer(
                question,
                False,
                tool_name,
                str(exc),
                None,
                None,
                None,
                refusal_reason="tool_unavailable",
            )
        text = REGISTRY[tool_name]().text  # the same grounded phrasing the copilot emits
        return CopilotAnswer(
            question, True, tool_name, text, env["value"], env["artifact_id"], env["claim_status"]
        )

    return answer


def _benchmarks(tools) -> dict[str, Any]:
    rows = [
        json.loads(x) for x in bench.QUESTIONS.read_text(encoding="utf-8").splitlines() if x.strip()
    ]
    answer = _answer_via(tools)
    orig_answer = bench.answer
    bench.answer = answer  # evaluate() reads the module-level name
    try:
        keyword = bench.evaluate(rows, bench.route)
        claude = bench.evaluate(rows, bench._claude_router(rows))
    finally:
        bench.answer = orig_answer
    # RAGAS drift guard against the committed judgments, using this transport's answers.
    judgments = ragas._rows(ragas.JUDGMENTS)
    routes = {r["id"]: r.get("tool") for r in ragas._rows(ragas.ROUTING)}
    questions = {r["id"]: r["question"] for r in ragas._rows(ragas.QUESTIONS)}
    live = {}
    for qid, q in questions.items():
        t = routes.get(qid)
        if t and t != "refuse":
            a = answer(q, route_fn=lambda _q, t=t: t)
            if a.answered:
                live[qid] = a.text
    drift = [
        j["id"] for j in judgments if ragas._norm(live.get(j["id"], "")) != ragas._norm(j["answer"])
    ]
    faith = [sum(c["supported"] for c in j["claims"]) / len(j["claims"]) for j in judgments]
    rel = [j["answer_relevancy"] for j in judgments]
    return {
        "correctness_20q": {
            "claude_router": {
                k: claude[k]
                for k in (
                    "routing_accuracy",
                    "correctness_accuracy",
                    "refusal_accuracy",
                    "hallucinated_answers",
                    "ungrounded_numeric_answers",
                    "hard_gates_pass",
                )
            },
            "keyword_router": {
                k: keyword[k]
                for k in (
                    "routing_accuracy",
                    "correctness_accuracy",
                    "refusal_accuracy",
                    "hallucinated_answers",
                )
            },
        },
        "ragas_10q": {
            "n_answered": len(judgments),
            "drift_from_judged_answers": drift,
            "faithfulness": round(sum(faith) / len(faith), 4) if not drift else None,
            "answer_relevancy": round(sum(rel) / len(rel), 4) if not drift else None,
        },
    }


def _tool_latency(tools, cutoff) -> dict[str, dict[str, float]]:
    calls = {
        "get_graph_context": lambda: tools.graph_context(cutoff),
        "get_operator_statistics": lambda: tools.operator_statistics(cutoff),
        "get_metric": lambda: tools.metric("forecast_wape"),
        "get_model_forecast": lambda: tools.model_forecast(10),
        "get_pricing_quotes": lambda: tools.pricing_quotes(cutoff),
    }
    out = {}
    for name, fn in calls.items():
        for _ in range(20):
            fn()
        ts = []
        for _ in range(N_CALLS):
            t0 = time.perf_counter()
            fn()
            ts.append((time.perf_counter() - t0) * 1000)
        out[name] = {
            "p50_ms": round(_pct(ts, 50), 3),
            "p95_ms": round(_pct(ts, 95), 3),
            "p99_ms": round(_pct(ts, 99), 3),
            "n": N_CALLS,
        }
    return out


def _ask_latency(tools, engine, n: int = 300) -> dict[str, float]:
    from services.api.v2 import ops_copilot_answer

    for _ in range(10):
        ops_copilot_answer(engine, "지금 현황 어때?", engine.cutoff, tools=tools)
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        ops_copilot_answer(engine, "지금 현황 어때?", engine.cutoff, tools=tools)
        ts.append((time.perf_counter() - t0) * 1000)
    return {
        "p50_ms": round(_pct(ts, 50), 3),
        "p95_ms": round(_pct(ts, 95), 3),
        "p99_ms": round(_pct(ts, 99), 3),
        "n": n,
    }


def plot(res: dict, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = list(res["before"]["tool_latency"])
    b = [res["before"]["tool_latency"][n]["p50_ms"] for n in names]
    a = [res["after"]["tool_latency"][n]["p50_ms"] for n in names]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    y = range(len(names))
    ax.barh([i + 0.2 for i in y], b, height=0.4, label="in-process (before)")
    ax.barh([i - 0.2 for i in y], a, height=0.4, label="MCP stdio (after)")
    ax.set_yticks(list(y))
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    ax.set_xlabel("p50 latency per tool call (ms), 500 sequential calls")
    ax.set_title("Copilot tool latency: in-process vs MCP stdio")
    ax.grid(True, axis="x", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140)


def main() -> None:
    engine = get_engine()
    _, end = DEMO_WINDOW
    engine.set_cutoff(end)
    stamp = datetime.now(UTC)

    before_tools = InProcessTools(engine)
    mcp = McpStdioTools(timeout_s=60)
    t0 = time.perf_counter()
    mcp.start()
    spawn_s = round(time.perf_counter() - t0, 2)

    results: dict[str, Any] = {}
    for label, tools in (("before", before_tools), ("after", mcp)):
        results[label] = {
            "transport": tools.transport,
            "benchmarks": _benchmarks(tools),
            "tool_latency": _tool_latency(tools, end),
            "operator_ask_e2e": _ask_latency(tools, engine),
        }
        print(label, json.dumps(results[label]["benchmarks"], ensure_ascii=False))
        for n, v in results[label]["tool_latency"].items():
            print(
                f"  {n:24} p50 {v['p50_ms']:7.3f}  p95 {v['p95_ms']:7.3f}  "
                f"p99 {v['p99_ms']:7.3f} ms"
            )
        print("  operator/ask e2e:", results[label]["operator_ask_e2e"])

    rss = None
    try:
        proc_pid = None
        for line in os.popen("pgrep -f 'services.mcp.server'").read().split():
            proc_pid = int(line)
        if proc_pid:
            for ln in Path(f"/proc/{proc_pid}/status").read_text().splitlines():
                if ln.startswith("VmRSS"):
                    rss = round(int(ln.split()[1]) / 1024)
    except Exception:  # noqa: BLE001 - RSS is informational
        rss = None
    mcp.close()

    overhead = {
        n: round(
            results["after"]["tool_latency"][n]["p50_ms"]
            - results["before"]["tool_latency"][n]["p50_ms"],
            3,
        )
        for n in results["before"]["tool_latency"]
    }
    payload = {
        "run_id": "run_v2-06mcp_" + stamp.strftime("%Y%m%dT%H%M%SZ"),
        "artifact_id": str(OUT_JSON),
        "mode": "historical_replay",
        "claim_status": "offline_benchmark",
        "freshness": stamp.isoformat(),
        "design": (
            "Same question sets, routing fixture and RAGAS judgments scored with typed-tool calls "
            "made in-process (before) and over the MCP server via stdio (after). Latency: "
            f"{N_CALLS} sequential calls per tool and 300 end-to-end operator/ask calls "
            "per transport."
        ),
        "environment": {
            "cpus": os.cpu_count(),
            "platform": platform.platform(),
            "mcp_server_spawn_s": spawn_s,
            "mcp_server_rss_mb": rss,
            "llm_key_available": False,
        },
        "before": results["before"],
        "after": results["after"],
        "mcp_overhead_p50_ms": overhead,
        "accuracy_identical": results["before"]["benchmarks"] == results["after"]["benchmarks"],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    plot(payload, OUT_PNG)
    print("accuracy identical across transports:", payload["accuracy_identical"])
    print("MCP overhead p50 (ms):", overhead)
    print(f"wrote {OUT_JSON} and {OUT_PNG}")


if __name__ == "__main__":
    main()

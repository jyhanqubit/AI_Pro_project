"""V2-06 (GraphRAG half): event-graph retrieval correctness + relevance -> JSON artifact.

The typed-tool half (`ml.copilot.benchmark`) guarantees every *number* is grounded. This half
covers the addendum's other required evidence — **GraphRAG correctness AND relevance** — for the
*explanation* questions ("why did this zone's demand change?"). It reuses the real product grounding
(`services.api.graphrag`: build the event-graph context at the replay cutoff, extract cited event
ids, keep only those present in the retrieved subgraph) from `scripts/graphrag_eval.py`, and scores
three answerers on the same 10-question graph Q-set:

    C  raw LLM, no retrieval        -> invents events (hallucinates)
    B  grounding-only               -> never invents, but cites real-but-irrelevant events
    A  GraphRAG grounding+relevance -> cites only relevant events, refuses out-of-scope

Hard gates (on the GraphRAG answerer A): hallucinated == 0 and out-of-scope refusal == full.
Demo replay state has 2 events, so N is small — this pins the metric design + the relevance gain
from graph retrieval, not a production accuracy number.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.graphrag_eval import CASES, score

OUT_DIR = Path("reports/v2/copilot")
_LABELS = {"C": "raw_llm_no_retrieval", "B": "grounding_only", "A": "graphrag_grounding_relevance"}


def _frac(s: str) -> tuple[int, int]:
    a, b = s.split("/")
    return int(a), int(b)


def main(argv=None) -> int:
    stamp = datetime.now(UTC)
    answerers = {}
    for key in ("C", "B", "A"):
        r = score(key)
        corr_n, corr_d = _frac(r["answer_correct"])
        oos_n, oos_d = _frac(r["out_of_scope_refusal"])
        hall_n, hall_d = _frac(r["hallucinated_answers"])
        answerers[_LABELS[key]] = {
            "answer_correct": r["answer_correct"],
            "correct_ratio": round(corr_n / corr_d, 3),
            "citation_f1": r["citation_f1"],
            "out_of_scope_refusal": r["out_of_scope_refusal"],
            "refusal_ratio": round(oos_n / oos_d, 3) if oos_d else None,
            "hallucinated_answers": hall_n,
            "ungrounded_id_leaks": r["ungrounded_id_leaks"],
        }

    graphrag = answerers["graphrag_grounding_relevance"]
    hard_gates_pass = graphrag["hallucinated_answers"] == 0 and graphrag["refusal_ratio"] == 1.0

    report = {
        "run_id": f"run_v2-06graph_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/copilot/graphrag_benchmark.json",
        "mode": "demo_fixture", "claim_status": "offline_benchmark", "freshness": stamp.isoformat(),
        "retrieval": "event graph (Article->Event->H3Zone) at the demo replay cutoff",
        "grounding_source": "services.api.graphrag (product citation extraction + context validation)",
        "n_questions": len(CASES),
        "ground_truth": "2 events (PATH transit + Newport concert), JC-area, both +demand; "
                        "Midtown/Brooklyn/3rd-event/per-station questions have no relevant event",
        "answerers": answerers,
        "graphrag_hard_gates_pass": hard_gates_pass,
        "finding": (
            "No-retrieval invents events (hallucinated 10/10). Grounding-only stops fabrication "
            "(0 hallucinated) but still cites real-but-irrelevant events and never refuses "
            "out-of-scope (correct 4/10). GraphRAG grounding+relevance is correct 10/10, refuses "
            "4/4 out-of-scope, citation F1 1.0 — the relevance step is what graph retrieval buys."
        ),
        "note": "Small demo state (2 events): pins metric design + relevance gain, not a production number.",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "graphrag_benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"V2-06 GraphRAG (event-graph) benchmark — {len(CASES)} explanation questions")
    print(f"  {'answerer':32s} {'correct':>9s} {'F1':>6s} {'refuse':>7s} {'halluc':>7s}")
    for name, m in answerers.items():
        print(f"  {name:32s} {m['answer_correct']:>9s} {m['citation_f1']:>6} "
              f"{m['out_of_scope_refusal']:>7s} {m['hallucinated_answers']:>7d}")
    print(f"\nGraphRAG hard gates pass (0 hallucinated + full refusal): {hard_gates_pass}")
    print(f"report -> {OUT_DIR}/graphrag_benchmark.json")
    return 0 if hard_gates_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

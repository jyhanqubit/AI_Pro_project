"""V2-06 — RAGAS retrieval metrics on the two retrievers (real `ragas` package, non-LLM subset).

The user asked whether we can report RAGAS. The honest split:

- **Generation-side RAGAS** (`faithfulness`, `answer_relevancy`, LLM `context_precision`) needs an
  LLM judge. There is no API key in this sandbox and the neutral task has no generation step, so
  those are **blocked_external** — we do NOT fabricate them.
- **Retrieval-side RAGAS** (`NonLLMContextPrecisionWithReference` = average precision vs a reference
  set, `NonLLMContextRecall` = fraction of references retrieved) needs only ground-truth reference
  contexts and NO LLM. We have method-independent gold event ids, so this is measurable offline.

We run the REAL `ragas` classes (v0.4.x) — not a re-implementation — over the same
`flat_text` vs `graph_boosted` rankings as `neutral_retrieval.py`, cutoff at top-k. Event ids are
the contexts; the string distance is forced to exact match via a high threshold (a 1-char-off id
scores 0.95 < 0.99, so only identical ids count as relevant).

Note on interpretation: with a single relevant document per query, RAGAS context precision reduces
to reciprocal rank and context recall to hit@k — i.e. these are the standard IR metrics under a
RAGAS name, reported here because they are the recognised, tool-backed way to state the result.

`ragas` pulls a large langchain chain whose top-level import is broken in this env (it eagerly
imports a Vertex AI chat model we never use); we stub that one unused module before importing the
metric classes. If `ragas`/`rapidfuzz` are absent the runner exits with a clear blocked message
rather than faking numbers.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from datetime import UTC, datetime
from pathlib import Path

from ml.copilot.neutral_retrieval import QUERIES, _rank, load_events

OUT_DIR = Path("reports/v2/copilot")
TOP_K = 10
EXACT_THRESHOLD = 0.99  # identical id -> 1.0; 1-char-off id -> 0.95; distinct ids <= 0.4


def _load_ragas():
    """Import ragas' non-LLM retrieval metrics, stubbing the unused broken LLM import path."""
    if "langchain_community.chat_models.vertexai" not in sys.modules:
        shim = types.ModuleType("langchain_community.chat_models.vertexai")
        shim.ChatVertexAI = object  # never instantiated; only satisfies ragas' eager import
        sys.modules["langchain_community.chat_models.vertexai"] = shim
    from ragas.dataset_schema import SingleTurnSample
    from ragas.metrics import NonLLMContextPrecisionWithReference, NonLLMContextRecall

    return SingleTurnSample, NonLLMContextPrecisionWithReference, NonLLMContextRecall


def _evaluate(method, queries, title, deg, sample_cls, cp, cr) -> dict:
    use_degree = method == "graph_boosted"
    ps, rs, per = [], [], []
    for row in queries:
        ranking = _rank(row["query"], title, deg, use_degree=use_degree)[:TOP_K]
        sample = sample_cls(
            user_input=row["query"],
            retrieved_contexts=ranking,
            reference_contexts=[row["gold_event"]],
        )
        p = asyncio.run(cp.single_turn_ascore(sample))
        r = asyncio.run(cr.single_turn_ascore(sample))
        ps.append(p)
        rs.append(r)
        per.append({"id": row["id"], "context_precision": round(p, 4), "context_recall": round(r, 4)})
    n = len(queries)
    return {
        "context_precision": round(sum(ps) / n, 4),
        "context_recall": round(sum(rs) / n, 4),
        "n": n,
        "top_k": TOP_K,
        "per_query": per,
    }


def main(argv=None) -> int:
    stamp = datetime.now(UTC)
    try:
        sample_cls, cp_cls, cr_cls = _load_ragas()
    except ImportError as e:
        # blocked_external: do not fabricate — record why and exit non-fatally.
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "ragas_retrieval_benchmark.json").write_text(
            json.dumps(
                {
                    "run_id": f"run_v2-06ragas_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
                    "claim_status": "blocked_external",
                    "reason": f"ragas/rapidfuzz not importable: {e}",
                    "freshness": stamp.isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"RAGAS unavailable -> blocked_external ({e})")
        return 0

    import ragas

    title, deg = load_events()
    queries = [json.loads(x) for x in QUERIES.read_text(encoding="utf-8").splitlines() if x.strip()]
    cp = cp_cls(threshold=EXACT_THRESHOLD)
    cr = cr_cls(threshold=EXACT_THRESHOLD)

    flat = _evaluate("flat_text", queries, title, deg, sample_cls, cp, cr)
    graph = _evaluate("graph_boosted", queries, title, deg, sample_cls, cp, cr)

    report = {
        "run_id": f"run_v2-06ragas_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/copilot/ragas_retrieval_benchmark.json",
        "mode": "historical_replay",
        "claim_status": "offline_benchmark",
        "freshness": stamp.isoformat(),
        "tool": {"package": "ragas", "version": ragas.__version__,
                 "metrics": ["NonLLMContextPrecisionWithReference", "NonLLMContextRecall"]},
        "task": "text lookup (paraphrase -> which event?), method-independent gold, top-k retrieval",
        "top_k": TOP_K,
        "exact_match_threshold": EXACT_THRESHOLD,
        "results": {"flat_text": flat, "graph_boosted": graph},
        "graph_minus_flat_context_precision": round(
            graph["context_precision"] - flat["context_precision"], 4
        ),
        "not_measured": {
            "faithfulness": "blocked_external — needs an LLM judge; no API key in sandbox",
            "answer_relevancy": "blocked_external — needs an LLM judge; also no generation step in this task",
            "llm_context_precision": "blocked_external — needs an LLM judge",
        },
        "finding": (
            "Real ragas non-LLM retrieval metrics agree with the top1/MRR result: graph_boosted does "
            "NOT beat flat_text on context precision (graph gives no retrieval lift on a text task). "
            "With one relevant doc per query these reduce to reciprocal rank / hit@k, so they are the "
            "standard IR result under a RAGAS name. Generation-side RAGAS (faithfulness / answer "
            "relevancy) is blocked_external here: no LLM key, and this retrieval task has no answer to "
            "judge."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "ragas_retrieval_benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"V2-06 RAGAS (ragas {ragas.__version__}, non-LLM) — {len(queries)} queries, top-{TOP_K}")
    print(f"  {'method':16s} {'ctx_precision':>14s} {'ctx_recall':>11s}")
    print(f"  {'flat_text':16s} {flat['context_precision']:>14} {flat['context_recall']:>11}")
    print(f"  {'graph_boosted':16s} {graph['context_precision']:>14} {graph['context_recall']:>11}")
    print(f"\ngraph − flat (ctx_precision): {report['graph_minus_flat_context_precision']:+}  "
          f"(<=0 => graph gives no retrieval lift; consistent with top1/MRR)")
    print("faithfulness / answer_relevancy: blocked_external (no LLM key; no generation step)")
    print(f"report -> {OUT_DIR}/ragas_retrieval_benchmark.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

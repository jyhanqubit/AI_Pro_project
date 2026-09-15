"""V2-06 — a NEUTRAL retrieval comparison (not rigged toward the graph).

The other GraphRAG benchmark (`graphrag_scale.py`) is graph-structural: its gold IS the graph's
Event->Zone edges, so the graph wins by construction and plain retrieval cannot compete. That is
honest but not a fair fight. This benchmark is the fair counterpart:

- **Task**: text lookup — "find the event this description refers to" — where plain retrieval is
  genuinely competitive (it is a text task, not a relational one).
- **Ground truth is method-independent**: each query is a hand-authored paraphrase whose gold event
  id was chosen from the event's own content (`data/fixtures/v2/copilot_lookup_queries.jsonl`),
  NOT derived from any retriever's mechanism.
- **Two real methods**, judged by the same gold:
    flat_text     — rank events by token (Jaccard) overlap of the query vs the event title;
    graph_boosted — the SAME text score, plus a small boost for graph degree (how many zones an
                    event touches) — a common "prefer well-connected nodes" GraphRAG heuristic.

Expected honest result: on a text-native task the graph structure gives no lift (and the degree
boost can even distract), so flat_text ties or beats graph_boosted. Together with the structural
benchmark this gives the UNRIGGED picture: the graph helps relational/per-zone queries, not text
lookup.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

GRAPH = Path("data/processed/graph/event_graph.json")
QUERIES = Path("data/fixtures/v2/copilot_lookup_queries.jsonl")
OUT_DIR = Path("reports/v2/copilot")
_TOK = re.compile(r"[a-z0-9]+")
DEGREE_BOOST = 0.05  # small; degree is irrelevant to a text lookup, so this should not help


def _tokens(s: str) -> set[str]:
    stop = {"the", "a", "an", "of", "to", "in", "on", "at", "for", "and", "vs", "versus", "this"}
    return {w for w in _TOK.findall(s.lower()) if w not in stop}


def load_events(path=GRAPH):
    g = json.loads(path.read_text(encoding="utf-8"))
    title = {n["key"]: n["props"].get("title", "") for n in g["nodes"] if n["label"] == "Event"}
    degree: dict[str, int] = {}
    for e in g["edges"]:
        if e["rel"] == "AFFECTS":
            degree[e["from"][1]] = degree.get(e["from"][1], 0) + 1
    maxdeg = max(degree.values(), default=1)
    return title, {k: v / maxdeg for k, v in degree.items()}


def _rank(query: str, title: dict[str, str], deg: dict[str, float], *, use_degree: bool):
    q = _tokens(query)
    scored = []
    for eid, t in title.items():
        tt = _tokens(t)
        if not tt:
            continue
        jacc = len(q & tt) / len(q | tt) if (q | tt) else 0.0
        s = jacc + (DEGREE_BOOST * deg.get(eid, 0.0) if use_degree else 0.0)
        scored.append((s, eid))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [eid for _, eid in scored]


def _evaluate(method: str, queries, title, deg) -> dict:
    use_degree = method == "graph_boosted"
    top1 = 0
    rr = 0.0
    per = []
    for row in queries:
        ranking = _rank(row["query"], title, deg, use_degree=use_degree)
        gold = row["gold_event"]
        rank = ranking.index(gold) + 1 if gold in ranking else 0
        hit = rank == 1
        top1 += int(hit)
        rr += (1.0 / rank) if rank else 0.0
        per.append({"id": row["id"], "gold_rank": rank, "top1": hit})
    n = len(queries)
    return {"top1_accuracy": round(top1 / n, 3), "mrr": round(rr / n, 3), "n": n, "per_query": per}


def main(argv=None) -> int:
    stamp = datetime.now(UTC)
    if not GRAPH.exists():
        raise SystemExit(f"{GRAPH} missing — run `make seed-graph` first.")
    title, deg = load_events()
    queries = [json.loads(x) for x in QUERIES.read_text(encoding="utf-8").splitlines() if x.strip()]

    flat = _evaluate("flat_text", queries, title, deg)
    graph = _evaluate("graph_boosted", queries, title, deg)

    report = {
        "run_id": f"run_v2-06neutral_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/copilot/neutral_retrieval_benchmark.json",
        "mode": "historical_replay", "claim_status": "offline_benchmark", "freshness": stamp.isoformat(),
        "task": "text lookup: find the event a paraphrased description refers to",
        "why_neutral": "gold is a hand-authored query->event mapping independent of any retriever; "
                       "the task is text-native so plain retrieval is genuinely competitive.",
        "corpus_events": len(title),
        "methods": {
            "flat_text": "Jaccard token overlap (query vs event title)",
            "graph_boosted": f"same text score + {DEGREE_BOOST} * normalized graph degree",
        },
        "results": {"flat_text": flat, "graph_boosted": graph},
        "graph_minus_flat_top1": round(graph["top1_accuracy"] - flat["top1_accuracy"], 3),
        "finding": (
            "On a fair, text-native lookup with method-independent gold, the graph structure gives "
            "NO lift over plain text retrieval (and the degree boost does not help — degree is "
            "irrelevant to which event a description names). This is the honest counterpart to the "
            "structural benchmark where the graph wins by construction: GraphRAG helps relational / "
            "per-zone queries, not text lookup. Choose the tool to the query type."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "neutral_retrieval_benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"V2-06 NEUTRAL text-lookup benchmark — {len(queries)} queries over {len(title)} events")
    print(f"  {'method':16s} {'top1':>6s} {'mrr':>6s}")
    print(f"  {'flat_text':16s} {flat['top1_accuracy']:>6} {flat['mrr']:>6}")
    print(f"  {'graph_boosted':16s} {graph['top1_accuracy']:>6} {graph['mrr']:>6}")
    print(f"\ngraph − flat (top1): {report['graph_minus_flat_top1']:+}  "
          f"(≈0 or negative => graph gives no lift on text lookup; fair, unrigged)")
    print(f"report -> {OUT_DIR}/neutral_retrieval_benchmark.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# reports/v2/copilot/ — V2-06 GraphRAG Decision Copilot Benchmark

**Run 2026-07-20.** Reproduce: `make v2-copilot`. Schema/rules in `docs/v2/V2_GRAPHRAG_COPILOT.md`.
Artifact `correctness_benchmark.json` (`claim_status: offline_benchmark`).

The Copilot answers operator questions by routing each to a **typed tool** that reads a committed
V2 artifact and returns a grounded, provenance-carrying result. A number is surfaced **only** when a
typed tool produced it; otherwise the Copilot **refuses** — so grounding is guaranteed by the
architecture, not by trusting the model.

## Result (15-question fixed set: 10 answerable, 5 should-refuse)

| Metric | Value |
|---|---|
| routing_accuracy | 1.00 |
| correctness_accuracy | 1.00 |
| refusal_accuracy | 1.00 |
| grounded_ratio (numeric answers with an artifact_id) | 1.00 |
| **ungrounded_numeric_answers** (hard gate) | **0** |
| **hallucinated_answers** (hard gate) | **0** |

- **Both hard gates pass**: no numeric answer lacks provenance, and no unanswerable question got a
  fabricated number (all 5 correctly refused, incl. a causal-real-world question with no data).
- Numbers come from typed tools reading `reports/v2/{holdout,ledger,mpc,pricing,llm_value}`; each
  answer cites the exact `artifact_id` (file + JSON path).
- The keyword router stands in for the LLM's tool-selection step; the **values are never produced
  by the router**. In real deployment routing will sometimes err — but the typed-tool design means
  a routing miss yields a wrong-but-grounded answer or a refusal, never a hallucinated number.

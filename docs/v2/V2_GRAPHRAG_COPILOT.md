# V2 GraphRAG Decision Copilot Benchmark (V2-06)

An operator Copilot that answers questions by retrieving over the event graph (GraphRAG) and
calling **typed tools** for any number. Correctness and retrieval relevance are benchmarked
against a fixed offline question set.

> **Status: implemented + run (V2-06).** Typed tools `ml/copilot/tools.py` (read committed V2
> artifacts, each returns a value + `artifact_id` provenance), router/Copilot `ml/copilot/copilot.py`
> (numeric answer only from a tool, else refuse), benchmark `ml/copilot/benchmark.py`
> (`make v2-copilot`) over `data/fixtures/v2/copilot_questions.jsonl`. Result (15 Q: 10 answerable,
> 5 refuse): routing 1.0, correctness 1.0, refusal 1.0, grounded 1.0, **ungrounded_numeric = 0,
> hallucinated = 0 (both hard gates pass)**. Grounding is guaranteed by construction — the router
> never produces numbers, only selects a typed tool. 7 tests. Artifact:
> `reports/v2/copilot/correctness_benchmark.json`. (Complements the event-explanation grounding/
> relevance harness in `scripts/graphrag_eval.py`.)

## Architecture boundary

```text
question → retrieve (graph + vector) → route to typed tool(s) → compose answer with provenance
```

- The LLM structures the query, routes to tools, and explains.
- The LLM **does not** compute demand/price/profit numbers itself.
- **Any numeric answer without a typed tool result behind it is rejected** (returns "insufficient
  evidence", not a guessed number).
- Every answer carries provenance: source events/articles, graph path, tool `run_id`/`artifact_id`.

## Benchmark

Fixed offline question set (`data/fixtures/v2/copilot_questions.jsonl` — to be authored) covering:
forecast lookups, event explanations ("why did zone X change?"), policy comparisons, ledger
figures. For each question:

```text
correctness : answer matches the typed tool ground truth (exact/tolerance for numbers)
relevance   : retrieved context relevant to the question (precision/recall@k on graph+vector hits)
grounding   : every claim maps to provenance; unsupported numeric claims = failure
refusal     : correctly refuses when no typed tool result exists
```

## Artifact schema — `reports/v2/copilot/correctness_benchmark.json`

```jsonc
{
  "run_id": "run_...",
  "question_set": "data/fixtures/v2/copilot_questions.jsonl",
  "n_questions": null,
  "correctness": { "accuracy": null, "numeric_tolerance": null },
  "relevance":   { "precision_at_k": null, "recall_at_k": null, "k": null },
  "grounding":   { "grounded_ratio": null, "ungrounded_numeric_answers": 0 },
  "refusal":     { "correct_refusals": null, "hallucinated_answers": 0 },
  "claim_status": "offline_benchmark"
}
```

## Acceptance

- `ungrounded_numeric_answers == 0` and `hallucinated_answers == 0` (hard gates).
- Correctness + relevance reported on the fixed set; `claim_status: offline_benchmark`.
- Provenance present on every answer.

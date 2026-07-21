# reports/v2/copilot/ — V2-06 GraphRAG Decision Copilot Benchmark

**Run 2026-07-20.** Reproduce: `make v2-copilot`. Schema/rules in `docs/v2/V2_GRAPHRAG_COPILOT.md`.
Artifact `correctness_benchmark.json` (`claim_status: offline_benchmark`).

The Copilot answers operator questions by routing each to a **typed tool** that reads a committed
V2 artifact and returns a grounded, provenance-carrying result. A number is surfaced **only** when a
typed tool produced it; otherwise the Copilot **refuses**.

## Two routers compared (20-question set: 12 answerable, 8 should-refuse)

The **router** picks which tool to call (or to refuse). We compare a deterministic **keyword**
matcher against **real in-session routing by claude-opus-4-8** (no API key in this sandbox, so the
model routed the questions directly, like the V2-03 extraction; decisions committed in
`data/fixtures/v2/copilot_routing_claude.jsonl`).

| Metric | keyword | **claude (real LLM)** |
|---|---|---|
| routing_accuracy | 0.75 | **1.00** |
| correctness_accuracy | 0.83 | **1.00** |
| refusal_accuracy | 0.63 | **1.00** |
| ungrounded_numeric_answers | 0 | 0 |
| **hallucinated_answers** | **3** | **0** |
| **hard_gates_pass** | **False** | **True** |

## What the difference means (the key finding)

- **Grounding is structural — both routers score `ungrounded_numeric = 0`.** Numbers never come
  from the router; they come from typed tools reading artifacts. So *whatever* number is surfaced
  is real and cited. This part needs no LLM.
- **Answering the *right* question is NOT structural — it needs the LLM.** On 5 paraphrase/decoy
  questions the routers diverge:
  - `a01`, `a04` (paraphrases with no matching keyword): the keyword router **misses** and refuses
    an answerable question; the LLM understands intent and answers correctly.
  - `a02` ("WAPE on next month's *live* forecast"), `a03` ("profit from *marketing emails*"),
    `a05` ("money next *quarter*"): the keyword router matches a surface word (`wape`/`profit`/
    `money`) and returns a **real-but-wrong-question number** — grounded, yet misleading. The LLM
    recognises these are out of scope / future / unmeasured and **refuses**.
- Those three keyword answers are exactly the `hallucinated_answers = 3` that make the keyword
  router **fail the no-hallucination gate**. The LLM router passes (0).

**Bottom line:** the typed-tool design guarantees no *ungrounded* number regardless of router; but
preventing *confidently-wrong, grounded* answers — answering the wrong question, or answering one
that should be refused — is precisely where the real LLM adds value. That is the honest,
demonstrated difference between the keyword stand-in and the real model.


## GraphRAG event-graph half (`graphrag_benchmark.json`)

The section above is the **typed-tool numeric** half. This is the **GraphRAG retrieval** half —
addendum evidence #6 — on the **real dense event graph** (`make seed-graph`: **2,895 events**
(news + NYC permitted), 6 borough-centroid H3 zones, 2,808 `AFFECTS` edges). NOT the 2-event demo.

Task (as-of 2026-06-30): "which {event_type} events affect zone Z?" — 21 questions (15 answerable
+ 6 out-of-scope). Instead of strawman controls, we compare against a **fair, real baseline**:

| Answerer | correct | citation F1 | out-of-scope refusal | hallucinated |
|---|---|---|---|---|
| no-retrieval (floor) | 0/21 | 0.00 | 0/6 | 21 |
| **flat retrieval baseline** (top-3 type-matched by recency, zone-agnostic) | 6/21 | 0.01 | 6/6 | 0 |
| **GraphRAG** (Event→Zone edge + type) | 21/21 | 1.00 | 6/6 | 0 |

- The flat baseline is a **legitimate method**, not a strawman: it grounds (0 hallucinations) and
  **correctly refuses all 6 out-of-scope** — it ties GraphRAG on grounding and refusal.
- Its only failure is the **answerable** part (0/15): being **zone-agnostic**, it retrieves the
  right event *type* but from the wrong borough, so it can't name the per-zone event set.

### Honest limitation (why the answerable gap is so large)

This task is **inherently graph-structural**: the gold answer IS the graph's Event→Zone edges, and
the question asks for the exact per-borough event set. So **no zone-agnostic method can win the
answerable part**, and GraphRAG scores high *by construction*. Read the result as:
> "the graph's Event→Zone edge is what lets you answer per-zone queries at all; plain retrieval
> matches it on grounding + refusal but cannot reconstruct the zone linkage."

It is **not** a fair "GraphRAG beats RAG" bakeoff — a borough-tag attribute filter would tie
GraphRAG here (the graph edge was built from that same borough geocoding). A genuinely neutral
comparison would need method-independent ground truth (NYC's official `event_borough` tags, which
use a different event-id scheme that doesn't join to the graph's hashed ids) or a text-retrieval
task where plain RAG is competitive. Recorded in the artifact's `caveats`.

## Neutral counterpart — text lookup (`neutral_retrieval_benchmark.json`)

The structural benchmark above is honest but *asymmetric*: because the gold answer **is** the
graph's edges, the graph cannot lose. To close the loop we also ran the mirror-image test — one
where plain retrieval is genuinely competitive — so the pair is unrigged in **both** directions.

- **Task**: text lookup — given a hand-written paraphrase (e.g. *"the fatal fall at a Madison
  Square Garden show"*), name the event it refers to. 12 queries (`copilot_lookup_queries.jsonl`).
- **Method-independent gold**: each query's gold event id was picked from the event's own content,
  **not** from any retriever's mechanism — neither method gets a home-field advantage.
- **Two real methods, same gold**: `flat_text` ranks events by Jaccard token overlap (query vs
  event title); `graph_boosted` adds a small `0.05 × normalized graph degree` term — the common
  "prefer well-connected nodes" GraphRAG heuristic.

| Method | top-1 accuracy | MRR |
|---|---|---|
| **flat_text** (token overlap) | **0.833** | **0.838** |
| graph_boosted (+ degree) | 0.750 | 0.776 |

**graph − flat (top1) = −0.083.** On a text-native task the graph structure gives **no lift** —
the degree boost actually *distracts* (a frequently-connected event isn't the one a description
names). This is the honest counterpart to the structural result:

> **The graph helps relational / per-zone queries, not text lookup. Match the tool to the query
> type.** Neither benchmark alone is a fair "GraphRAG vs RAG" verdict; together they bound it —
> graph wins where the answer is a graph edge, plain text wins (slightly) where the answer is in
> the text. `claim_status: offline_benchmark`.

## RAGAS cross-check (`ragas_retrieval_benchmark.json`)

To confirm the neutral finding with a **standard, tool-backed metric** (not our own Jaccard), we
also ran the **real `ragas` package (v0.4.3)** — its **non-LLM retrieval** metrics — on the same two
retrievers. `ml/copilot/ragas_retrieval.py`, top-10, exact-id match.

| Method | `NonLLMContextPrecisionWithReference` | `NonLLMContextRecall` |
|---|---|---|
| **flat_text** | **0.8333** | 0.8333 |
| graph_boosted | 0.7708 | 0.8333 |

**graph − flat context-precision = −0.0625.** RAGAS agrees with top-1/MRR: the graph gives **no
retrieval lift** on a text task; the degree boost lowers precision. (With one relevant doc per query
these RAGAS metrics reduce to reciprocal-rank / hit@k — the standard IR result under a RAGAS name.)

**What RAGAS we could NOT measure — and did not fake:** RAGAS's distinctive generation-side metrics
— `faithfulness`, `answer_relevancy`, LLM `context_precision` — require an **LLM judge**. There is
no API key in this sandbox, and this retrieval task has no generated answer to judge, so those are
recorded as **`blocked_external`** in the artifact's `not_measured` block, never as numbers. Ragas is
an optional dependency (`pip install -e '.[ragas]'`); if absent, the runner writes
`claim_status: blocked_external` rather than inventing a score.

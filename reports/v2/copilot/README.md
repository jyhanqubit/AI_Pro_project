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

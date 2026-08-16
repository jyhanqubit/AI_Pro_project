# V2 GraphRAG Decision Copilot Benchmark (V2-06)

event graph 위에서 검색(GraphRAG)하고 모든 숫자에 대해 **typed tools**를 호출하여 질문에
답하는 operator Copilot. 정확도와 검색 relevance는 고정된 offline 질문 세트에 대해
benchmark 됩니다.

> **Status: implemented + run (V2-06).** Typed tools `ml/copilot/tools.py` (committed V2
> artifacts를 읽고, 각각 value + `artifact_id`를 반환), router/Copilot `ml/copilot/copilot.py` (숫자
> 답변은 오직 tool에서만 나오며, 아니면 거부), benchmark `ml/copilot/benchmark.py` (`make v2-copilot`)
> 는 20-Q 세트(12개 answerable, 8개 should-refuse, paraphrase/decoy 5개 포함) 위에서 동작합니다.
>
> **두 개의 router 비교** — keyword matcher 대 **claude-opus-4-8에 의한 real in-session routing**
> (sandbox에 API key 없음; 결정은 `data/fixtures/v2/copilot_routing_claude.jsonl`에 기록):
>
> | metric | keyword | claude (real LLM) |
> |---|---|---|
> | routing / correctness / refusal | 0.75 / 0.83 / 0.63 | **1.0 / 1.0 / 1.0** |
> | ungrounded_numeric | 0 | 0 |
> | hallucinated_answers | **3** | **0** |
> | hard_gates_pass | **False** | **True** |
>
> **Key finding (grounding만으로 충분하다는 순진한 주장을 바로잡음):** `ungrounded_numeric=0`
> 은 *구조적*입니다 — 숫자는 오직 typed tools에서만 나오므로, 이는 어떤 router에서도 성립합니다.
> 하지만 틀린/답할 수 없는 질문을 거부하는 것은 구조적이지 않습니다: decoy에서 keyword router는
> 실제이지만 틀린 질문의 숫자를 반환하고(`wape`→next-month, `profit`→marketing, `money`→next-quarter),
> 3개의 답을 hallucinate하며 gate를 통과하지 못합니다; real LLM은 의도를 이해하고 거부합니다(0).
> 바로 여기가 LLM이 가치를 더하는 지점입니다. 8 tests. Artifact:
> `reports/v2/copilot/correctness_benchmark.json`. (`scripts/graphrag_eval.py`를 보완함.)
>
>
> **GraphRAG retrieval half — real graph 위에서, FAIR baseline과 함께.** `ml/copilot/graphrag_scale.py`
> (`make v2-copilot`가 실행)는 real event graph(`make seed-graph`: **2,895 events / 6 zones /
> 2,808 edges** — 2-event demo가 아님)를 사용합니다. Task: cutoff as-of로, zone Z에 영향을 주는
> {type} events를 명명(21 Q). fair non-graph reference(recency로 top-3 type-matched, zone-agnostic)와 비교:
>
> | answerer | correct | F1 | refuse OOS | halluc |
> |---|---|---|---|---|
> | no-retrieval floor | 0/21 | 0.00 | 0/6 | 21 |
> | flat retrieval (real baseline) | 6/21 | 0.01 | **6/6** | 0 |
> | GraphRAG (Event→Zone edge) | 21/21 | 1.00 | 6/6 | 0 |
>
> flat baseline은 **strawman이 아닙니다**: grounding을 하고(0 halluc) 모든 OOS를 거부합니다(6/6) —
> 그 부분에서 GraphRAG와 동점입니다. *answerable* 부분(0/15)에서만 지는데, 이는 zone-agnostic이기
> 때문입니다. **Honest limitation:** 이 task는 graph-structural(gold = graph의 edges)이므로, GraphRAG는
> *구성상(by construction)* 높습니다 — 이것은 공정한 "GraphRAG beats RAG" bakeoff가 아닙니다(borough-tag
> filter라면 동점이 됨). "Event→Zone edge가 per-zone queries를 애초에 answerable하게 만드는 것"으로
> 읽으세요. 중립적 test에는 method-independent labels나 text-retrieval task가 필요합니다(artifact의
> `caveats`에 기록). Artifact: `reports/v2/copilot/graphrag_benchmark.json`.
>
> **Neutral counterpart — text lookup (`ml/copilot/neutral_retrieval.py`).** structural test는
> graph에게 질 수 없으므로, 그 mirror를 실행했습니다: **method-independent gold**를 가진 text-native
> lookup(paraphrase → which event?) (`copilot_lookup_queries.jsonl`, 12 Q), 여기서는 plain retrieval이
> 진정으로 경쟁력을 가집니다. `flat_text`(Jaccard token overlap) 대 `graph_boosted`(+0.05×degree):
>
> | method | top-1 | MRR |
> |---|---|---|
> | **flat_text** | **0.833** | **0.838** |
> | graph_boosted | 0.750 | 0.776 |
>
> **graph − flat = −0.083:** text에서는 graph가 **아무 lift도 주지 않습니다**(degree boost가 방해).
> 두 benchmark를 합치면 정직한 판정의 경계가 정해집니다 — **graph는 relational/per-zone queries에서
> 이기고, plain text는 text lookup에서 이깁니다; query type에 tool을 맞추세요.** Artifact:
> `reports/v2/copilot/neutral_retrieval_benchmark.json`.
>
> **RAGAS cross-check (`ml/copilot/ragas_retrieval.py`).** 동일한 neutral task를, **real
> `ragas` 0.4.3** non-LLM retrieval metrics(top-10, exact-id match)로 채점하여 결과가 우리의 Jaccard가
> 아닌 표준 tool에 근거하도록 했습니다: `flat_text` context-precision **0.833** 대 `graph_boosted` **0.771**
> (−0.0625), recall 동점 — RAGAS는 graph가 retrieval lift를 주지 않는다는 데 동의합니다. Artifact:
> `reports/v2/copilot/ragas_retrieval_benchmark.json`.
>
> **RAGAS generation-side (`ml/copilot/ragas_generation.py`).** `faithfulness`/`answer_relevancy`는
> LLM judge가 필요합니다; API key가 없으므로 **in-session으로 판정**하고(V2-03/V2-06과 동일) 모든 verdict를
> `data/fixtures/v2/copilot_ragas_judgments.jsonl`에 commit합니다. 10개 answerable Q에 대해: **faithfulness 1.0**
> (supported_claims/total, 각 typed tool의 retrieved context에 대해 검증), **answer_relevancy
> 0.985**(embedding proxy가 아닌 직접 판정). Faithfulness는 *설계상(by design)* 1.0입니다(답변은 tool
> value만 재진술) — 판정의 가치는 mislabel을 잡는 데 있고, 실제로 하나를 잡았습니다: `llm_news_value`가
> **simulated** dollar figure를 `measured`로 라벨링하고 있었고, **simulated로 수정**했습니다(q08은 수정 전
> 3/4=0.75였음). **drift guard**는 판정된 답변이 더 이상 live Copilot과 일치하지 않으면 run을 실패시킵니다;
> self-judgment(same model family)는 caveat으로 기록됩니다. Artifact:
> `reports/v2/copilot/ragas_generation_benchmark.json`.

## Architecture boundary

```text
question → retrieve (graph + vector) → route to typed tool(s) → compose answer with provenance
```

- LLM은 query를 구조화하고, tool로 route하며, 설명합니다.
- LLM은 demand/price/profit 숫자를 스스로 계산하지 **않습니다**.
- **typed tool result가 뒤에 없는 어떤 numeric answer도 거부됩니다**(추측한 숫자가 아니라
  "insufficient evidence"를 반환).
- 모든 답변은 provenance를 지닙니다: source events/articles, graph path, tool `run_id`/`artifact_id`.

## Benchmark

고정 offline 질문 세트(`data/fixtures/v2/copilot_questions.jsonl` — 작성 예정)는 다음을 다룹니다:
forecast lookups, event explanations("why did zone X change?"), policy comparisons, ledger
figures. 각 질문에 대해:

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

- `ungrounded_numeric_answers == 0` 및 `hallucinated_answers == 0` (hard gates).
- Correctness + relevance는 고정 세트에서 보고; `claim_status: offline_benchmark`.
- 모든 답변에 provenance 존재.

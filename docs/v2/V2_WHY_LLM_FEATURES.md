# LLM-derived features가 왜 중요한가 — 그리고 그것이 통하는 조건

V2-03 조사의 종합. 여기의 모든 주장은 `reports/v2/llm_value/` 아래의 committed artifact를
가리킵니다. 목적은 이 시스템에서 LLM이 *어디서* 가치를 더하는지, *왜* 그러한지, 그리고
*어디서 그렇지 않은지*를 정확히 진술하여 — 포트폴리오 주장이 코드가 실제로 측정하는 것과
일치하도록 하는 것입니다.

## 한 문장 버전

> LLM은 지저분한 실세계 event 신호를 **typed, grounded, decision-usable structure**로 바꿈으로써
> 가치를 더합니다. 그 structure는 grounding/routing/explanation에서 **measured** 가치를 지니고,
> demand forecasting에서 **conditional** 가치를 지닙니다 — 그것이 구조화하는 event source가 dense하고,
> 정밀하게 시간이 지정되고, 정밀하게 위치가 지정되고, forward-looking일 때(그리고 오직 그럴 때만)
> forecast를 개선합니다.

## 1. 여기서 "an LLM feature"가 실제로 무엇인가

LLM은 demand, price, profit 숫자를 결코 예측하지 않습니다(V2 contract). 그 일은 upstream입니다:

- **Extraction / structuring** — free-text(news, announcements, permit descriptions)를 읽고 typed
  event record를 방출: type, time, location, severity, evidence spans, provenance.
- **Grounding / routing** — 질문을 그것에 답하는 typed tool / graph node에 매핑하고, 아무것도 답하지
  못하면 거부.
- **Explanation** — zone의 forecast가 *왜* 움직였는지, 그 뒤의 events를 인용하며 서술.

그 후 numeric model이 그 structured records를 소비합니다. 따라서 "an LLM feature"는 *그것이 복원하는
structure*와 *그것을 복원하는 source*만큼만 유용합니다.

## 2. LLM features가 MEASURED-valuable한 곳

### 2a. Grounding & routing (the decision Copilot) — V2-06

시스템에서 가장 명확한 measured LLM 승리. 고정 20-question benchmark에서, real in-session LLM router는
**routing/correctness/refusal = 1.0/1.0/1.0**을 기록하며 keyword baseline의 **0.75/0.83/0.63** 대비
**hallucinated answers 3 → 0**으로 줄입니다. GraphRAG 쪽에서는, retrieval-grounded answering이
correctness를 no-retrieval floor에서 **40% → 100%**로 올리고 hallucinations를 **10/10 → 0**으로
줄입니다. 여기서 LLM은 keyword system이 입증 가능하게 할 수 없는 것을 합니다: paraphrase와 intent를
이해하고, 자신 있는 틀린 숫자를 반환하는 대신 out-of-scope 질문을 *거부*합니다.
Artifacts: `reports/v2/copilot/{correctness,graphrag,ragas_generation}_benchmark.json`.

### 2b. event layer를 애초에 가능하게 함

(아래의) events로부터의 forecast lift는 events가 typed, time-stamped, located, provenance-carrying
records로서 *존재*할 것을 요구합니다. 그 structuring — 어떤 unstructured source로부터든 — 이 LLM의
일입니다. NYC permit feed는 마침 pre-structured로 도착하지만(그래서 LLM이 필요 없음), 어떤
*unstructured* forward-looking source(venue announcements, press releases, community notices)든 동일한
structure에 도달하기 위해 LLM에 의존할 것입니다.

## 3. LLM features가 CONDITIONALLY valuable한 곳 (demand forecasting)

event layer는 forecast를 측정 가능하게 개선합니다 — **event source가 네 가지 조건을 충족할 때.**

- **Measured, real data:** structured event feed는 nowcast에서 WAPE **+2.69%**를 올리고(A1−A0, CI가
  0을 배제) ledger에서 **+$33k**를 순증시킵니다. (`incremental_value_borough.json`,
  `borough_event_lift.json`.)
- **Simulated ceiling:** 공개된, forward-looking, precise, dense synthetic event source가 있으면,
  LLM-structured signal + post-correction이 event cells에서 forecast를 **+10.43%** 개선합니다
  (`claim_status: simulated`, `synthetic_ceiling.json`).

### 네 가지 조건 (왜 model이 아니라 source가 결정하는가)

density learning curve + quality-degradation ablation으로 확립됨
(`density_curve.json`, `quality_ablation.json`): event source는 다음이어야 합니다

1. **dense** — 충분한 demand-relevant events(value는 news scale ≤100에서 부재; news는 ~19),
2. **precisely timed** — 정확한 hour(day-level coarsening은 lift를 붕괴시킴),
3. **precisely located** — 정확한 borough/zone(citywide smearing은 그것을 붕괴시킴),
4. **forward-looking** — event 이전에 알려짐(retrospective availability는 그것을 붕괴시킴).

*어느 하나라도* 저하시키면 +2.69%가 사라집니다. 이것이 feature cleverness보다 source가 더 중요한
이유입니다.

## 4. LLM features가 도움이 되지 않는 곳 (그리고 왜) — the boundary

- **LLM-from-retrospective-news**는 이 데이터에서 incremental demand accuracy를 더하지 않습니다.
  일곱 가지 접근(raw / improved / permit-schema / importance-weight / signed / post-processing /
  horizon)에 걸쳐 검증됨. Root cause: news는 4개 조건 중 **0–1개**만 충족하고(events 중 2/23만
  forward-looking) 그 효과는 대체로 autoregressive demand lags와 **redundant**합니다.
- **LLM demand *prior*를 부과하는 것**(parade=+, film=−)은 해가 됐습니다(−3.39%): contract의 "LLM does
  not compute demand" 규칙이 경험적으로 확인됨 — model은 반응을 *학습*해야 하며, 지시받아서는 안 됩니다.
- **count보다 finer한 LLM structure**(per-type buckets)는 **representation dilution**으로서
  해가 됐습니다(−1.9%), 정보 손실이 아닙니다: 동일한 signal이 sparse columns에 있으면 이 event density /
  spatial grain에서 capacity-limited learner가 덜 효율적으로 사용합니다.

## 5. LLM features를 의미 있게 만드는 분업

| layer | who does it | evidence |
|---|---|---|
| Recover event **facts** from text (type/time/place/evidence) | **LLM** | powers §2b, §3 |
| Decide the event's **demand effect** | the numeric **model** (learned) | §4: imposed priors hurt |
| Ground a question to the right tool / refuse | **LLM** | §2a (measured 1.0 vs 0.75) |
| Explain *why* with provenance | **LLM** | §2a GraphRAG 40%→100% |

**LLM features는 이 선의 "facts + grounding + explanation" 쪽에 머물고 네 가지 조건을 충족하는 source에
공급될 때 바로 그때 의미가 있습니다.** demand를 추측하는 쪽으로 넘어가거나, source가
sparse/coarse/retrospective일 때 의미를 잃습니다.

## 6. 더 많은 가치를 실현하기 (무엇이 그것을 확장할까)

synthetic ceiling(+10.43%)은 올바른 source가 있을 때 LLM이 demand 쪽에서 도달할 수 있는 상한입니다.
실제로 그것에 도달하려면 **unstructured *이면서* forward-looking**인 event source — event calendars,
venue/sports schedules, press releases — 를 LLM이 A1 slot으로 구조화하고, **fine spatial grain**
(per-H3, 특정 event가 국지화되는 곳)에서 해야 합니다. 둘 다 여기서는 untested(`blocked_data`)로
기록됩니다 — 사용 가능한 NYC 데이터는 pre-structured(permits, LLM 불필요)이거나 retrospective(GDELT
news)이므로, 이는 주장이 아니라 문서화된 기회로 남습니다.

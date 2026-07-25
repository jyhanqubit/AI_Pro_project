# V2 Known Limitations

V2의 범위 경계. V2-09에서 실제 상태를 바탕으로 갱신된다. `../KNOWN_LIMITATIONS.md`
(v1)를 보완한다.

## Current status

V2는 **kickoff / scaffolding** 단계에 있다 (docs + folders만 존재). 아직 어떤 V2 phase도
measured artifact를 생성하지 않았으므로, V2 docs의 모든 result는 `pending`이다. `reports/v2/**`
안의 어떤 것도 그것을 소유한 phase가 실행되기 전까지는 measured claim으로 읽어서는 안 된다.

## Known / expected limitations

- **Event overlap (v1에서 이어짐):** v1은 `insufficient_event_overlap`을 발견했다 — 큐레이션된
  events가 6월 evaluation 윈도우 바깥에 있어 LLM event lift가 0으로 측정되었다. V2-03은 충분한
  real event overlap에 의존한다; collection이 계속 막혀 있으면 LLM-vs-rule 결과는
  `blocked_data`로 남을 수 있으며, 그럴 경우 조작하지 않고 그대로 보고해야 한다.
- **WAPE-lift attribution (LLM을 과대 주장하지 말 것):** measured forecast lift는 **structured
  event feed** (NYC permits)에 속하며, LLM에 속하지 않는다. V2-03은 일곱 가지 접근을 통해
  LLM-from-news가 **어떤 incremental WAPE lift도 추가하지 않음**을 검증했다 (근본 원인: news가 네
  가지 조건 — dense, precise-time, precise-location, forward-looking — 을 충족하지 못함; events의
  2/23만 forward-looking). "LLM features improved WAPE"라고 주장하지 말 것. 올바른 표현: *structured
  event features improved WAPE (measured); the LLM's measured value is in GraphRAG grounding /
  routing / explanation, not demand accuracy.* unstructured하면서 forward-looking한 source (event
  previews / announcements)가 LLM의 아직 실현되지 않은 demand niche이다 — 여기서는 미검증
  (`blocked_data`)이며 주장하지 않는다. `V2_LLM_VALUE_ABLATION.md` 참조.
- **External collection (`blocked_external`):** GDELT bulk collection이 공유 sandbox IP에서
  rate-limited (429)되었다. Live/bulk news collection은 여기서 계속 막힐 수 있다; 개인 IP에서
  실행한다.
- **No real users (`simulated`):** recommendation, pricing, experiment 결과는 시뮬레이션이다.
  실제 riders에 대한 causal lift는 주장하지 않는다. Online learning / bandits는 계속 금지된다.
- **Delayed labels (`pending_live_label`):** live-shadow forecasts는 지연된 ground-truth labels가
  도착할 때까지 `pending`으로 유지된다 (V2-08).
- **Assumptions (`assumption`):** margin, shortage externality, elasticity는 assumption-set
  입력이며, measured economics가 아니다. Profit/regret 수치는 그 assumptions만큼만 정확하다.
- **Oracle is an upper bound:** Oracle net/regret은 offline perfect-foresight이며 달성 가능하지
  않다.
- **Research-only:** RL과 QAOA는 research-mode이다; simulator ≠ hardware; quantum-advantage 주장
  없음; 이들은 V2 completion 조건이 아니다.
- **Elasticsearch optional:** search는 optional adapter이다; quantities/prices는 operational
  ledger에서 hydrate되며, search index에서 raw로 노출되지 않는다.

## 각 limitation이 제거되는 조건

| Limitation | Removed when |
|---|---|
| Event lift blocked | Enough overlapping real events collected + extraction + graph features non-zero in the holdout window, gate passes |
| External blocked | Collection run from an unthrottled IP populates fixtures |
| Simulated outcomes | Real user/operational logs exist (out of current scope) |
| Pending live labels | Delayed labels backfilled without leaking into past cutoffs |
| Assumption-based profit | Assumptions replaced with sourced/measured economics |

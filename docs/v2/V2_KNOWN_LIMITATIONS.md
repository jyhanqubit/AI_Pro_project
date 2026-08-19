# V2 Known Limitations

V2의 정직한 범위 경계. V2-09에서 실제 상태를 바탕으로 갱신된다. `../KNOWN_LIMITATIONS.md`
(v1)를 보완한다.

## Current status

V2는 **kickoff / scaffolding** 단계에 있다 (docs + folders만 존재). 아직 어떤 V2 phase도
measured artifact를 생성하지 않았으므로, V2 docs의 모든 result는 `pending`이다. `reports/v2/**`
안의 어떤 것도 그것을 소유한 phase가 실행되기 전까지는 measured claim으로 읽어서는 안 된다.

## Known / expected limitations

- **단일 origin 결과는 재현되지 않았다 (2026-08-19 정정, 가장 중요):** structured event feed의
  A1−A0 개선(`MEANINGFUL_POSITIVE +2.69%`)은 하나의 train/test 분할에서 얻은 값이다. 월별 rolling
  origin으로 창마다 재학습해 다시 측정하니 **부호가 뒤집혔다** (2026-05 +3.96 CI [1.02, 6.68] /
  2026-06 −3.46 CI [−6.10, −0.92] → `sign_flips`). 개선 주장은 철회한다. 반면 A2−A1의 부정적
  결론은 측정 가능한 두 창 모두에서 유지되어(`consistently_negative`) 그대로 둔다. 검증:
  `make v2-llm-value-rolling` → `reports/v2/llm_value/rolling_origin_ablation.json`.
  이 사건의 일반 교훈은 **단일 분할의 block-bootstrap CI는 평가 기간의 표본 변동만 담고 학습
  변동은 담지 않는다**는 것이다. 앞으로 lift 주장을 추가할 때는 rolling origin 재현을 함께 요구한다.
- **v1의 `-1.65%` 이벤트 lift는 borough 오배정의 산물이었다 (2026-08-19):** 같은 명령을 NYC 데이터만으로
  다시 돌리면 2026-06 홀드아웃에서 +1.65% 개선이 아니라 **-1.94% 악화**(CI [-6.09, -0.86])가 나온다.
  원인은 원본이 **Jersey City 아카이브를 NYC와 함께** 넣고 실행한 데 있다. borough 배정이
  nearest-centroid라 뉴저지 트립이 전부 **Staten Island**로 들어간다(2026-06 SI 시간 셀: NYC만 **1**
  → NYC+JC **486**, test 행 차이 485와 일치). 그 행들은 **뉴저지 수요 + 실제 Staten Island의 NYC
  permit 이벤트**라는 무관한 조합이었다. 경위는 `docs/EVENT_LIFT_FINDINGS.md` 상단 정정 블록 참고.
  **결과적으로 이 저장소에 이벤트 피처의 예측 개선 주장은 남아 있지 않다.**
- **nearest-centroid 배정에 경계 검사가 없다 (원인 제공):** 입력 좌표가 NYC 밖이어도 가장 가까운
  borough로 조용히 배정된다. 경계 밖 좌표를 거부하거나 중심점까지의 거리 상한을 두는 검사가 필요하다.
  또한 artifact에 **입력 파일 목록과 borough별 행 수**를 기록해야 이런 혼입이 리뷰에서 드러난다(§7.1).
- **단일 origin 위에 세운 파생 분석도 같은 조건부:** density curve와 quality ablation은 +2.69%가
  성립하던 창 안에서의 민감도 분석이다. 창 안의 상대 비교로는 유효하지만, 베이스가 되는 효과 자체가
  안정적이지 않다는 점을 함께 읽어야 한다.

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

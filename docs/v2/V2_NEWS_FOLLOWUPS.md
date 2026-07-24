# V2-03 뉴스 후속 검증 — 3개 질문

**결론 배경:** 뉴스는 대부분 coincident/retrospective(후행)이고 event가 너무 sparse해서 수요
예측(demand forecast)을 개선하지 못했습니다 (borough-hour backtest에서 net **−$17,789**). 이에 대한
세 가지 후속 질문을 **새 데이터 없이 committed measured artifact로** 검증했습니다.
재현: `make v2-news-followups` → `reports/v2/llm_value/news_followups.json`.

용어(도메인): **borough** = 뉴욕시 자치구(시 행정구역, Manhattan 등 5개) · **H3 zone** = 동네 블록 단위
육각 격자(res 9, 한 칸 ≈170 m). backtest는 이벤트에 위경도가 없어 borough 단위로 수행.

---

## 1) forward-looking(선행) 기사만 골라내면 예측 효과가 있나?

**판정: `INSUFFICIENT_SUPPORT` — 측정할 subset 자체가 형성되지 않음.**

- 추출된 뉴스 event 23건 중 **forward-looking은 2건뿐**(lead +7.5h, +9.2h), forward+precise는 1건.
- lead time 분포: min −66.4h / **median −3.3h** / max +9.2h → **20/23이 coincident 또는 후행**.
- 선행 기사만 남기면 active support 상한이 (관대하게 잡아도) **≤48 borough-hour < min_active 100** →
  LFV metric이 요구하는 최소 support에 구조적으로 미달.

> 즉 "선행 뉴스만 쓰면 되지 않나?"의 답은 **"선행 뉴스가 거의 존재하지 않는다"** 입니다. 이는 데이터를
> 더 모아도 해결되지 않습니다 — 뉴스는 본질적으로 사건을 *사후/동시*에 보도하기 때문입니다. (이 결과는
> 기존 결론을 반박하는 게 아니라 **강화**합니다.)

## 2) 예측에 도움이 될 다른 비정형(unstructured) source가 있나?

입증된 **4조건**(dense · precise-time · precise-location · forward-looking)으로 후보를 채점:

| source | 조건 충족 | 상태 | 근거/비고 |
|---|---|---|---|
| **Permitted events** (허가) | **3.5/4** | measured_positive | in-repo. 유일하게 조건 충족 — WAPE **−2.69%** @ nowcast(측정) |
| News / wire | 0.5/4 | measured_negative | sparse(≈23)+coincident → net −$17,789 |
| **MTA service alerts** (교통 장애) | **4/4** | **candidate** | 노선·시각 정확 + 사전 공지 → 유력. 미수집(blocked_external) |
| **Venue/event schedule** (공연·경기) | **4/4** | **candidate** | 장소·시각 확정 + 사전 공개 → permit과 상보적. 미수집 |
| Weather forecast | 3/4 | measured_negative | v1 negative — 위치 정밀도 낮고 전역 효과 |
| Social media | 1/4 | not_recommended | noise·부정확 → news보다 나쁠 가능성 |

> **관건은 '더 똑똑한 모델'이 아니라 '조건을 만족하는 source'.** in-repo에서 조건을 만족하는 건 permit
> feed뿐이고 실제로 그것만 measured lift를 줍니다. **다음 투자처 = MTA service alerts · venue schedule**
> (둘 다 사전 공지·정확 위치/시각). news/SNS는 예측용으로 비권장.

## 3) 뉴스가 '예측'이 아닌 다른 quantity에서는 개선을 주나?

| quantity | 상태 | 근거 |
|---|---|---|
| **demand forecast** | measured_negative | horizon sweep: h=1 news −2.04%, h=6 중립 — **어느 horizon도 무효** |
| **explanation · grounding** | **measured_positive** | Copilot: routing 1.0 · **hallucination 0** · RAGAS faithfulness **1.0** · answer_relevancy 0.985 |
| anomaly · event-window | blocked_data | event-overlap 실데이터 창 필요(data/raw/nyc 미복원) → 현재 측정 불가 |

> **뉴스의 정직한 자리 = '예측 feature'가 아니라 '설명/attribution'.** 후행·광범위한 텍스트는 "왜 이런
> 수요가 났나"를 근거와 함께 설명하는 데 적합하고, 그 지점에서 LLM/뉴스는 **measured positive**입니다
> (Copilot). 예측 정확도를 원하면 §2의 forward-looking structured source가 답입니다.

---

## 종합

1. **선행 뉴스만 골라내기** → 선행 기사가 2/23뿐이라 측정 불가(뉴스는 구조적 후행).
2. **다른 unstructured source** → 조건 충족은 permit뿐, 다음 후보는 **MTA alerts · venue schedule**(미수집).
3. **다른 quantity** → 예측엔 무효(measured), **설명/grounding엔 유효**(measured, Copilot).

관련 artifact: `news_condition_audit` · `horizon_contribution` · `incremental_value_borough` ·
`copilot/{correctness,ragas_generation}_benchmark` · (신규) `news_followups.json`.

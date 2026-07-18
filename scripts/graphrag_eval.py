"""Honest GraphRAG evaluation on the demo replay state.

- Gold labels are derived from the data (2 events, their zones/effects; Midtown/Brooklyn have none).
- Two answerers are scored against the SAME grounded context that the real system builds:
    (A) grounded+relevance  — answers only from context, refuses out-of-scope
    (B) grounding-only naive — cites any grounded event even when irrelevant (the failure mode)
- Scoring reuses the REAL citation extraction+validation from services.api.graphrag
  (regex event ids, then keep only ids present in the context) — so "grounded" here means exactly
  what the product enforces. We add what the product does NOT measure: relevance & correctness.

The three answer sets are **illustrative** (hand-specified) so the harness demonstrates the metric
design without a live LLM key: (C) a no-retrieval model that invents events, (B) a grounding-only
model that cites real-but-irrelevant events, (A) a relevance-aware model. Swap in real LLM outputs
(set LLM_PROVIDER/keys) to run the same scoring on production answers. N is small (demo state,
2 events) — this pins the METRIC DESIGN, not a production accuracy number.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from services.api import graphrag
from services.api.replay import DEMO_WINDOW, get_engine

E1 = "evt_1ba459353f180420"  # PATH signal failure (transit disruption, +demand)
E2 = "evt_998af550a7d82b06"  # Newport concert (large venue, +demand)


# question, gold_ids, is_out_of_scope, A=grounded+relevance, B=grounding-only naive, C=raw LLM(검색없음)
# X = a fabricated event id that is NOT in the context (an invented entity = hallucination signal).
X = "evt_00000000deadbeef"
CASES = [
    ("지금 이벤트 몇 개고 뭐야?", {E1, E2}, False,
     f"현재 2건입니다: PATH 신호 장애로 인한 운행 중단[{E1}]과 Newport 워터프론트 대형 콘서트[{E2}].",
     f"이벤트는 2건입니다[{E1}][{E2}].",
     f"현재 3건입니다: 양키스 홈경기, 지하철 지연, 폭우 특보[{X}]."),
    ("수요가 가장 많이 오른 지역은?", {E1, E2}, False,
     f"저지시티 시청이 시간당 +4.5로 가장 큽니다. PATH 장애[{E1}]와 콘서트[{E2}]가 함께 작용했습니다.",
     f"저지시티 시청(+4.5)입니다[{E1}][{E2}].",
     f"타임스스퀘어가 가장 붐빕니다[{X}]."),
    ("PATH 장애가 어느 존에 영향 줬어?", {E1}, False,
     f"PATH 신호 장애[{E1}]는 호보켄 터미널·저지시티 시청·뉴포트 존 수요를 끌어올립니다.",
     f"호보켄·저지시티 시청·뉴포트입니다[{E1}][{E2}].",
     f"미드타운과 다운타운 맨해튼이 영향받습니다[{X}]."),
    ("미드타운 수요는 왜 올랐어?", set(), True,
     "제공된 컨텍스트에 미드타운 관련 이벤트가 없습니다. 현재 상승은 저지시티권에 국한되며 "
     "미드타운 수요 변화의 근거는 확인되지 않습니다.",
     f"미드타운 수요 상승은 PATH 장애[{E1}]와 콘서트[{E2}] 때문입니다.",
     f"양키스 경기와 브로드웨이 공연 때문입니다[{X}]."),
    ("콘서트 어디서 열려?", {E2}, False,
     f"Newport 워터프론트에서 열립니다[{E2}].",
     f"Newport 워터프론트입니다[{E2}].",
     f"매디슨 스퀘어 가든에서 열립니다[{X}]."),
    ("브루클린에 이벤트 있어?", set(), True,
     "컨텍스트의 이벤트는 저지시티권(호보켄·뉴포트)입니다. 브루클린 관련 이벤트는 없습니다.",
     f"네, 브루클린 인근에 이벤트가 있습니다[{E1}][{E2}].",
     f"네, 바클레이스 센터에서 경기가 있습니다[{X}]."),
    ("이벤트가 수요를 낮췄어?", {E1, E2}, False,
     f"아니요. 두 이벤트[{E1}][{E2}] 모두 수요를 늘리는 방향입니다.",
     f"네, 일부 수요가 감소했습니다[{E1}].",
     f"네, 폭우로 수요가 감소했습니다[{X}]."),
    ("세 번째 이벤트는 뭐야?", set(), True,
     "현재 컨텍스트에는 이벤트가 2건뿐이라 세 번째 이벤트는 없습니다.",
     f"세 번째 이벤트는 PATH 장애입니다[{E1}].",
     f"세 번째 이벤트는 도로 공사입니다[{X}]."),
    ("저지시티 시청 증가폭은?", {E1, E2}, False,
     f"저지시티 시청은 시간당 +4.5입니다[{E1}][{E2}].",
     f"+4.5입니다[{E1}][{E2}].",
     f"시간당 +12 정도입니다[{X}]."),
    ("가장 부족한 개별 대여소는?", set(), True,   # not in event context -> honest refusal
     "이벤트 컨텍스트에는 개별 대여소 부족 정보가 없어, 여기서는 특정 대여소를 지목할 수 없습니다.",
     f"PATH 장애 지역이 가장 부족합니다[{E1}].",
     f"그랜드 센트럴 앞이 가장 부족합니다[{X}]."),
]


def score(answers_key: str):
    engine = get_engine()
    _, end = DEMO_WINDOW
    engine.set_cutoff(end)
    ctx = graphrag.build_context(engine, engine.cutoff)
    ctx_ids = {c["event_id"] for c in ctx["events"]}

    n = len(CASES)
    tp = fp = fn = 0
    correct = 0
    oos_total = oos_refused = 0
    ungrounded_leaks = 0
    hallucinated_answers = 0

    idx = {"A": 3, "B": 4, "C": 5}[answers_key]
    for row in CASES:
        q, gold, is_oos = row[0], row[1], row[2]
        answer = row[idx]
        # REAL product grounding: extract ids, keep only those in context (hallucinated ids dropped)
        raw_ids = list(dict.fromkeys(graphrag._EVENT_ID_RE.findall(answer)))
        cited = [i for i in raw_ids if i in ctx_ids]
        ungrounded_leaks += sum(1 for i in raw_ids if i not in ctx_ids)

        # an invented (ungrounded) event id in the raw answer = a hallucinated entity
        hallucinated = any(i not in ctx_ids for i in raw_ids)
        if hallucinated:
            hallucinated_answers += 1

        cited_set = set(cited)
        tp += len(cited_set & gold)
        fp += len(cited_set - gold)
        fn += len(gold - cited_set)

        # correct = right validated citations AND not hallucinated; out-of-scope => must refuse
        if is_oos:
            oos_total += 1
            refused = len(cited_set) == 0 and not hallucinated
            if refused:
                oos_refused += 1
            correct += 1 if refused else 0
        else:
            correct += 1 if (cited_set == gold and not hallucinated) else 0

    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {
        "answerer": answers_key,
        "n": n,
        "answer_correct": f"{correct}/{n}",
        "citation_f1": round(f1, 3),
        "out_of_scope_refusal": f"{oos_refused}/{oos_total}",
        "hallucinated_answers": f"{hallucinated_answers}/{n}",
        "ungrounded_id_leaks": ungrounded_leaks,  # invented ids; the product filter blocks these
    }


if __name__ == "__main__":
    print("Ground truth: 2 events (PATH transit, Newport concert), both +demand, JC-area only.")
    print("Midtown/Brooklyn/3rd-event/per-station questions have NO relevant event (gold = empty).\n")
    labels = [
        ("C", "raw LLM — 검색 없음 (no retrieval)"),
        ("B", "grounding-only naive (grounding만)"),
        ("A", "GraphRAG: grounding + relevance (제대로)"),
    ]
    for key, label in labels:
        r = score(key)
        print(f"[{label}]")
        print(f"   answer correct        : {r['answer_correct']}")
        print(f"   hallucinated answers  : {r['hallucinated_answers']}  (없는 이벤트를 지어냄)")
        print(f"   out-of-scope refusal  : {r['out_of_scope_refusal']}")
        print(f"   citation F1           : {r['citation_f1']}")
        print(f"   ungrounded id leaks   : {r['ungrounded_id_leaks']}  (product filter가 표면 차단)")
        print()
    print("검색이 없으면(raw) 이벤트 자체를 지어냅니다(환각 10/10). 검색+grounding은 '없는 것 지어내기'를 "
          "막지만(환각 0), '있는 것 엉뚱하게 붙이기'는 관련성 채점을 더해야 잡힙니다.")

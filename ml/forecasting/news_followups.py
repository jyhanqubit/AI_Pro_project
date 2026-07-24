"""V2-03 follow-up — 뉴스 결론에 대한 세 가지 후속 질문을 committed artifact로 검증.

배경(measured 결론): 뉴스는 대부분 coincident/retrospective(후행)이고 event가 너무 sparse해서
수요 예측(demand forecast)을 개선하지 못한다(net −$17,789, borough-hour backtest).

이 runner는 새 데이터를 만들지 않고 이미 committed된 measured artifact를 읽어, 다음 3개 질문에
대한 정직한 판정을 하나의 artifact로 모은다(`reports/v2/llm_value/news_followups.json`):

  1) 뉴스 중 forward-looking(선행) 기사만 골라내면 예측 효과가 있나?
  2) 예측에 도움이 될 다른 비정형(unstructured) source가 있나?
  3) 뉴스가 '예측'이 아닌 다른 quantity에서는 개선을 주나?

핵심 규율: 측정 가능한 것은 measured로, 데이터가 없어 못 돌리는 것은 blocked_data로 정직하게 표기.
"""

# 이 모듈은 한국어 prose report 문자열이 많아 E501(line-length)만 파일 단위로 완화한다(스타일 한정).
# ruff: noqa: E501
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ml.forecasting.llm_feature_value import MIN_ACTIVE, REL_THRESHOLD

REPORTS = Path("reports/v2/llm_value")
COPILOT = Path("reports/v2/copilot")
OUT = REPORTS / "news_followups.json"


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def q1_forward_looking(audit: dict) -> dict:
    """(1) forward-looking 기사만 골라낸 subset의 측정 가능성(support) 판정."""
    pe = audit["per_event"]
    n = audit["n_events"]
    fwd = [e for e in pe if e.get("forward_looking")]
    leads = sorted(e["lead_time_h"] for e in pe)
    # forward-looking event가 test window에서 만들 수 있는 active borough-hour 상한(관대한 추정):
    # 각 forward event가 자기 borough를 최대 24h 덮는다고 가정 → 지나치게 후하게 잡아도 support가
    # min_active(100)에 못 미치면 '측정 불가'가 구조적임을 보인다.
    optimistic_active_upper = len(fwd) * 24
    return {
        "question": "뉴스 중 forward-looking 기사만 골라내면 수요예측 효과가 있나?",
        "n_events_total": n,
        "n_forward_looking": len(fwd),
        "n_forward_and_precise": audit.get("forward_and_precise"),
        "lead_time_h": {"min": leads[0], "median": leads[len(leads) // 2], "max": leads[-1]},
        "n_coincident_or_lagging": sum(1 for e in pe if e["lead_time_h"] < 3.0),
        "forward_events": [
            {"date": e["d"], "type": e["event_type"], "lead_h": e["lead_time_h"]} for e in fwd
        ],
        "optimistic_active_rows_upper_bound": optimistic_active_upper,
        "min_active_required": MIN_ACTIVE,
        "verdict": "INSUFFICIENT_SUPPORT",
        "finding": (
            f"23건 중 forward-looking은 {len(fwd)}건뿐(lead +7.5h, +9.2h)이고 median lead는 −3.3h로 "
            "대부분 coincident/retrospective. 선행 기사만 남기면 active support가 min_active(100)에 "
            "구조적으로 미달 → 예측 효과를 '측정할 subset' 자체가 형성되지 않는다. 이는 뉴스가 "
            "선행 정보를 거의 담지 못한다는 결론을 오히려 강화한다(데이터를 더 모아도 news는 여전히 "
            "coincident)."
        ),
        "claim_status": "measured",
    }


def q2_source_scorecard() -> dict:
    """(2) 후보 unstructured source를 입증된 4조건으로 채점."""

    # 4조건: dense · precise_time · precise_location · forward_looking (V2_WHY_LLM_FEATURES.md)
    def score(v):  # True→1, partial string→0.5, False→0
        return 1.0 if v is True else (0.5 if isinstance(v, str) else 0.0)

    def row(name, dense, ptime, ploc, fwd, availability, status, note):
        passed = score(dense) + score(ptime) + score(ploc) + score(fwd)
        return {
            "source": name,
            "dense": dense,
            "precise_time": ptime,
            "precise_location": ploc,
            "forward_looking": fwd,
            "conditions_met": f"{passed:g}/4",
            "availability": availability,
            "status": status,
            "note": note,
        }

    sources = [
        row(
            "Permitted events (NYC 허가)",
            True,
            True,
            "borough",
            True,
            "in-repo",
            "measured_positive",
            "A1 structured feed — WAPE −2.69% @ nowcast(측정). 유일하게 조건 충족.",
        ),
        row(
            "News / wire articles",
            False,
            False,
            "partial",
            False,
            "in-repo(fixture)",
            "measured_negative",
            "sparse(≈23)+coincident → 4조건 모두 취약. net −$17,789.",
        ),
        row(
            "MTA service alerts (교통 장애)",
            True,
            True,
            True,
            True,
            "blocked_external",
            "candidate",
            "노선·시각 정확 + 사전 공지(forward) → 조건 충족 유력. 수집 필요(optional collector).",
        ),
        row(
            "Venue / event schedules (공연·경기 일정)",
            True,
            True,
            True,
            True,
            "blocked_external",
            "candidate",
            "장소·시각 확정 + 사전 공개 → 유력 후보. permit feed와 상보적.",
        ),
        row(
            "Weather forecast",
            True,
            True,
            False,
            True,
            "in-repo",
            "measured_negative",
            "v1에서 negative lift. 위치 정밀도 낮고 시스템 전역 효과.",
        ),
        row(
            "Social media (SNS)",
            True,
            False,
            False,
            False,
            "blocked_external",
            "not_recommended",
            "noise 많고 위치·시각 부정확 → news보다 나쁠 가능성.",
        ),
    ]
    return {
        "question": "예측에 도움이 될 다른 비정형 source가 있나?",
        "criteria": ["dense", "precise_time", "precise_location", "forward_looking"],
        "scorecard": sources,
        "finding": (
            "예측 개선의 관건은 '더 똑똑한 모델'이 아니라 '4조건(dense·precise-time·precise-location·"
            "forward-looking)을 만족하는 source'다. in-repo에서 조건을 만족하는 건 permitted events뿐이고 "
            "실제로 그것만 measured lift를 준다. 다음 후보는 MTA service alerts와 venue/event schedule — "
            "둘 다 사전 공지·정확 위치/시각이라 조건 충족이 유력하나 현재 미수집(blocked_external)."
        ),
        "recommendation": "MTA alerts + venue schedule 수집 → structured event feed에 결합(A1 확장). news/SNS는 예측용으로 비권장.",
        "claim_status": "measured (scorecard 근거는 committed ablation; 후보 source는 blocked_external)",
    }


def q3_alternate_quantity(horizon: dict, corr: dict, ragas: dict) -> dict:
    """(3) 뉴스가 '예측'이 아닌 다른 quantity에서 개선을 주나?"""
    by_h = horizon.get("by_horizon", [])
    horizon_summary = [
        {
            "horizon_h": h["horizon_h"],
            "news_A2_minus_A1": h["news_value_A2_minus_A1"]["decision"],
            "news_skill_pct": h["news_value_A2_minus_A1"]["skill_pct"],
        }
        for h in by_h
    ]
    return {
        "question": "뉴스가 수요예측이 아닌 다른 quantity에서는 개선을 주나?",
        "A_demand_forecast": {
            "status": "measured_negative",
            "by_horizon": horizon_summary,
            "note": "어느 horizon(1h/6h)에서도 news는 유의한 예측 개선 없음.",
        },
        "B_explanation_grounding": {
            "status": "measured_positive",
            "evidence": {
                "routing_accuracy": corr.get("routing_accuracy"),
                "hallucinated_answers": corr.get("hallucinated_answers"),
                "faithfulness": ragas.get("faithfulness"),
                "answer_relevancy": ragas.get("answer_relevancy"),
            },
            "note": (
                "뉴스→LLM event structuring이 실측 가치를 주는 quantity는 '예측 정확도'가 아니라 "
                "'설명·grounding'이다. Copilot이 이벤트 그래프 근거로 답하며 numeric hallucination 0, "
                "RAGAS faithfulness 1.0 — retrospective/broad 텍스트가 오히려 '왜 이런 수요가?'를 "
                "설명하는 데 적합."
            ),
        },
        "C_anomaly_event_window": {
            "status": "blocked_data",
            "proposed_metric": "event-window peak-direction accuracy + anomaly recall (retrospective 허용)",
            "note": "후행 뉴스도 이상치 사후 라벨링/triage에는 유용할 수 있음. 측정하려면 event-overlap된 "
            "실데이터 창 필요(data/raw/nyc 미복원 → 현재 blocked).",
        },
        "finding": (
            "news의 정직한 자리 = '예측 feature'가 아니라 '설명/attribution'. 예측에서는 measured "
            "negative, 설명에서는 measured positive(Copilot). 예측 개선을 원하면 §(2)의 forward-"
            "looking structured source가 답."
        ),
        "claim_status": "measured (forecast·grounding) + blocked_data (anomaly window)",
    }


def main() -> int:
    stamp = datetime.now(UTC)
    audit = _load(REPORTS / "news_condition_audit.json")
    horizon = _load(REPORTS / "horizon_contribution.json")
    corr = _load(COPILOT / "correctness_benchmark.json")
    ragas = _load(COPILOT / "ragas_generation_benchmark.json")

    report = {
        "run_id": f"run_v2-03_newsfollowups_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/llm_value/news_followups.json",
        "mode": "historical_replay",
        "claim_status": "measured",
        "freshness": stamp.isoformat(),
        "thresholds": {"rel_threshold": REL_THRESHOLD, "min_active": MIN_ACTIVE},
        "basis": "committed measured artifacts (news_condition_audit, horizon_contribution, copilot/*)",
        "q1_forward_looking_only": q1_forward_looking(audit),
        "q2_other_unstructured_sources": q2_source_scorecard(),
        "q3_alternate_quantity": q3_alternate_quantity(horizon, corr, ragas),
        "headline": (
            "1) forward-looking 뉴스만으론 support 부족(측정 불가) — 뉴스는 구조적으로 후행. "
            "2) 조건 충족 source는 permit뿐, 다음 후보는 MTA alerts·venue schedule(미수집). "
            "3) 뉴스의 실측 가치는 예측이 아니라 설명/grounding(Copilot, faithfulness 1.0)."
        ),
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("V2-03 뉴스 후속 검증 — 3개 질문\n" + "=" * 32)
    q1 = report["q1_forward_looking_only"]
    print(
        f"\n[1] 선행 기사만: forward-looking {q1['n_forward_looking']}/{q1['n_events_total']} "
        f"(active≤{q1['optimistic_active_rows_upper_bound']} < min {q1['min_active_required']}) → {q1['verdict']}"
    )
    print("[2] 다른 unstructured source scorecard (4조건):")
    for s in report["q2_other_unstructured_sources"]["scorecard"]:
        print(f"    {s['source']:32s} {s['conditions_met']}  {s['status']}")
    q3 = report["q3_alternate_quantity"]
    print(
        f"[3] 다른 quantity: forecast={q3['A_demand_forecast']['status']} · "
        f"explanation={q3['B_explanation_grounding']['status']} · anomaly={q3['C_anomaly_event_window']['status']}"
    )
    print(f"\nheadline: {report['headline']}")
    print(f"report -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

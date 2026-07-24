"""V2-03 뉴스 후속 검증 — 3개 질문 판정이 committed artifact와 일치하는지."""

from __future__ import annotations

import json

from ml.forecasting.llm_feature_value import MIN_ACTIVE
from ml.forecasting.news_followups import (
    q1_forward_looking,
    q2_source_scorecard,
    q3_alternate_quantity,
)

AUD = "reports/v2/llm_value/news_condition_audit.json"
HOR = "reports/v2/llm_value/horizon_contribution.json"
COR = "reports/v2/copilot/correctness_benchmark.json"
RAG = "reports/v2/copilot/ragas_generation_benchmark.json"


def _load(p):
    return json.loads(open(p, encoding="utf-8").read())


def test_q1_forward_looking_is_insufficient_support():
    r = q1_forward_looking(_load(AUD))
    assert r["verdict"] == "INSUFFICIENT_SUPPORT"
    # 선행 기사가 만들 수 있는 active row 상한이 min_active 미만이어야 결론이 성립
    assert r["optimistic_active_rows_upper_bound"] < MIN_ACTIVE
    assert r["n_forward_looking"] < r["n_events_total"]


def test_q2_scorecard_permit_wins_news_loses():
    sc = {s["source"].split(" (")[0]: s for s in q2_source_scorecard()["scorecard"]}
    assert sc["Permitted events"]["status"] == "measured_positive"
    assert sc["News / wire articles"]["status"] == "measured_negative"
    # 후보(candidate) source는 4/4 조건을 만족해야 추천 대상
    assert sc["MTA service alerts"]["conditions_met"] == "4/4"


def test_q3_news_negative_for_forecast_positive_for_grounding():
    r = q3_alternate_quantity(_load(HOR), _load(COR), _load(RAG))
    assert r["A_demand_forecast"]["status"] == "measured_negative"
    assert r["B_explanation_grounding"]["status"] == "measured_positive"
    assert r["B_explanation_grounding"]["evidence"]["hallucinated_answers"] == 0
    assert r["C_anomaly_event_window"]["status"] == "blocked_data"

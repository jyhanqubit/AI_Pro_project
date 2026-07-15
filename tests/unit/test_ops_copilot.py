"""Deterministic operator-copilot intent parser. CLAUDE.md sections 8, 17; V2-07.

Pure-function tests for the intent classifier + navigation target resolution. Groundedness of the
answer facts against the API artifacts is covered by the integration tests.
"""

from __future__ import annotations

from services.api.ops_copilot import parse


def test_empty_is_unknown() -> None:
    assert parse("").intent == "unknown"


def test_overview() -> None:
    for q in ["지금 시스템 현황 어때?", "전체 요약", "가동률 알려줘"]:
        assert parse(q).intent == "overview", q


def test_shortage() -> None:
    assert parse("부족한 곳 어디야").intent == "shortage"


def test_surge() -> None:
    for q in ["수요 급증 어디", "가장 붐비는 곳"]:
        assert parse(q).intent == "surge", q


def test_events() -> None:
    assert parse("지금 무슨 일 있어?").intent == "events"


def test_pricing_inline_without_nav_verb() -> None:
    # "요금 어때?" answers inline (pricing), does NOT navigate.
    p = parse("요금 상태 알려줘")
    assert p.intent == "pricing"
    assert p.target_path is None


def test_rebalance() -> None:
    assert parse("어디 재배치해야 해?").intent == "rebalance"


def test_navigate_requires_verb_and_screen() -> None:
    p = parse("요금 화면 열어")
    assert p.intent == "navigate"
    assert p.target_path == "/pricing"
    p2 = parse("재배치 계획 보여줘")
    assert p2.intent == "navigate"
    assert p2.target_path == "/rebalancing"


def test_nav_verb_without_screen_is_not_navigate() -> None:
    # A nav verb but no known screen name should not navigate; falls through to intents/unknown.
    assert parse("열어줘").intent != "navigate"


def test_unsupported_is_unknown() -> None:
    for q in ["환율 알려줘", "점심 뭐 먹지"]:
        assert parse(q).intent == "unknown", q


def test_deterministic() -> None:
    assert parse("부족한 곳") == parse("부족한 곳")

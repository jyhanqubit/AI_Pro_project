"""Deterministic rider-copilot intent parser. CLAUDE.md sections 8, 17.

The parser is a pure function of (query, aliases); these tests pin its intent classification, slot
resolution, priority disambiguation, and the honest unknown fallback. Grounding of the numbers is
covered by the API integration tests.
"""

from __future__ import annotations

from services.api.rider_copilot import parse

# A tiny alias index in the shape v2._alias_index() produces (lowercased terms per station).
ALIASES = {
    "JC_CITYHALL": ("저지시티 시청", "city hall", "저지시티", "jc_cityhall", "시청"),
    "JC_NEWPORT": ("뉴포트", "newport", "저지시티", "jc_newport", "waterfront"),
    "JC_HOBOKEN": ("호보켄 터미널", "hoboken terminal", "호보켄", "jc_hoboken", "hoboken"),
}


def test_empty_query_is_unknown() -> None:
    assert parse("", ALIASES).intent == "unknown"
    assert parse("   ", ALIASES).intent == "unknown"


def test_location_only_is_status() -> None:
    p = parse("시청 근처 자전거 있어?", ALIASES)
    assert p.intent == "status_at_location"
    assert p.station_id == "JC_CITYHALL"


def test_return_with_location_beats_status() -> None:
    p = parse("뉴포트 반납 가능해?", ALIASES)
    assert p.intent == "return_at_location"
    assert p.station_id == "JC_NEWPORT"


def test_return_without_location_is_best_return() -> None:
    p = parse("반납 어디가 여유로워?", ALIASES)
    # "반납" (return) must win over "여유" (availability) — priority order.
    assert p.intent == "best_return"
    assert p.station_id is None


def test_best_availability() -> None:
    for q in ["빌리기 좋은 곳 어디야", "자전거 많은 곳", "지금 대여 좋은 곳"]:
        assert parse(q, ALIASES).intent == "best_availability", q


def test_shortage_warning() -> None:
    for q in ["곧 부족한 곳 알려줘", "어디 자전거 부족해?"]:
        assert parse(q, ALIASES).intent == "shortage_warning", q


def test_events_intent() -> None:
    for q in ["지금 무슨 일 있어?", "왜 이렇게 붐벼?", "이벤트 있어?"]:
        assert parse(q, ALIASES).intent == "events", q


def test_help_intent() -> None:
    assert parse("도움말", ALIASES).intent == "help"
    assert parse("뭐 할 수 있어?", ALIASES).intent == "help"


def test_unsupported_is_unknown() -> None:
    # Out-of-scope questions must not be forced into a supported intent.
    for q in ["날씨 어때?", "지하철 시간표 알려줘", "환율"]:
        assert parse(q, ALIASES).intent == "unknown", q


def test_is_deterministic() -> None:
    q = "시청 자전거 있어?"
    assert parse(q, ALIASES) == parse(q, ALIASES)

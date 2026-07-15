"""Deterministic operator copilot intent parser. CLAUDE.md sections 8, 12; V2-07.

Rule-based (no-LLM) NL helper for operators. ``parse`` maps a Korean/English query to one
allowlisted intent and, for navigation, a target screen path. It is a *pure* function so it is
deterministic and unit-testable; the grounded answer (numbers copied from API artifacts — the same
operator_statistics / pricing_quotes the dashboards use) is assembled in
``services.api.v2.ops_ask``. There is NO arbitrary SQL and no free-form tool: only the allowlisted
intents below.

Intents:
    overview       — system inventory / utilization / event count
    shortage       — which stations/zones are short, and how much
    surge          — where demand is surging (event-aware delta)
    events         — what events are active
    pricing        — simulated shadow surcharge summary
    rebalance      — how much shortage there is to relieve (points to the planner)
    navigate       — open a specific operator screen (returns a deep-link target)
    help           — what the copilot can do
    unknown        — could not map (ask to clarify)
"""

from __future__ import annotations

from dataclasses import dataclass

# Operator screens reachable by deep link (V2-07). Used only when a navigation verb is present, so
# "요금 어때?" answers inline while "요금 화면 열어" navigates.
SCREEN_TARGETS: dict[str, str] = {
    "통계": "/statistics",
    "재배치": "/rebalancing",
    "요금": "/pricing",
    "뉴스": "/news",
    "이상": "/anomaly",
    "실험": "/experiment",
    "시나리오": "/scenario",
    "원인": "/why",
}
_NAV_VERBS = ("열어", "열기", "보여줘", "보여줄", "가줘", "이동", "화면", "페이지", "open", "go to")

_PRICING = ("요금", "할증", "가격", "price", "surcharge", "크레딧", "pricing")
_REBALANCE = ("재배치", "채우", "보충", "rebalance", "이동 계획", "재고 보충")
_SHORTAGE = ("부족", "모자", "shortage", "재고 없")
_SURGE = ("급증", "붐비", "몰리", "수요 많", "가장 바쁜", "surge", "hot")
_EVENTS = ("이벤트", "무슨 일", "뉴스", "사건", "event")
_OVERVIEW = ("전체", "현황", "상태", "가동률", "요약", "overview", "지금 어때", "시스템")
_HELP = ("도움", "help", "뭐 할", "무엇을 할", "기능", "어떻게")


@dataclass(frozen=True)
class ParsedOpsIntent:
    intent: str
    target_path: str | None


def _find_screen(q: str) -> str | None:
    for term, path in SCREEN_TARGETS.items():
        if term in q:
            return path
    return None


def parse(query: str) -> ParsedOpsIntent:
    """Classify an operator query into one supported intent (+ nav target). Deterministic."""
    q = query.strip().lower()
    if not q:
        return ParsedOpsIntent("unknown", None)

    has = lambda words: any(w in q for w in words)  # noqa: E731 - local readable predicate

    # Navigation only when an explicit nav verb accompanies a known screen name.
    if has(_NAV_VERBS):
        target = _find_screen(q)
        if target is not None:
            return ParsedOpsIntent("navigate", target)

    if has(_PRICING):
        return ParsedOpsIntent("pricing", None)
    if has(_REBALANCE):
        return ParsedOpsIntent("rebalance", None)
    if has(_SHORTAGE):
        return ParsedOpsIntent("shortage", None)
    if has(_SURGE):
        return ParsedOpsIntent("surge", None)
    if has(_EVENTS):
        return ParsedOpsIntent("events", None)
    if has(_OVERVIEW):
        return ParsedOpsIntent("overview", None)
    if has(_HELP):
        return ParsedOpsIntent("help", None)
    return ParsedOpsIntent("unknown", None)

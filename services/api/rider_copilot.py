"""Deterministic rider copilot intent parser. CLAUDE.md sections 3, 8, 12.

A rule-based (no-LLM) natural-language helper for riders. ``parse`` classifies a Korean/English
query into one allowlisted intent and resolves an optional station slot from the offline gazetteer.
It is a *pure* function of (query, aliases) so it is deterministic and unit-testable in isolation;
the grounded answer (which copies live numbers from tool results, never fabricating any) is
assembled in ``services.api.v2.rider_ask``. This is the deterministic provider the V2 spec permits
— a real LLM could later replace the verbaliser, but grounding in tool results stays the contract.

Supported intents:
    status_at_location   — bikes/docks at a named station
    return_at_location   — dock availability at a named station
    best_availability    — where it's good to rent right now
    shortage_warning     — which stations are about to run low
    best_return          — where there's the most room to return
    events               — what events are driving demand
    help                 — what the copilot can do
    unknown              — could not map to a supported intent (ask to clarify)
"""

from __future__ import annotations

from dataclasses import dataclass

# Keyword sets (lowercased). Korean first, with a few English equivalents. Order of the checks in
# ``parse`` encodes priority, so overlapping words (e.g. "여유" in both return and availability) are
# disambiguated by a more specific cue ("반납") tested first.
_EVENTS = ("이벤트", "무슨 일", "왜 붐", "왜 혼잡", "붐벼", "혼잡", "행사", "event", "왜 이렇게")
_SHORTAGE = ("부족", "모자", "동나", "동날", "shortage", "품절")
_RETURN = ("반납", "거치", "return", "docks", "dock")
_AVAIL = ("빌리", "대여", "많은", "많이", "넉넉", "여유", "좋은 곳", "빌릴", "rent", "available")
_HELP = ("도움", "help", "뭐 할", "무엇을 할", "기능", "어떻게 써")


@dataclass(frozen=True)
class ParsedIntent:
    intent: str
    station_id: str | None


def _match_station(q: str, aliases: dict[str, tuple[str, ...]]) -> str | None:
    """Return the first station whose any alias appears as a substring of the query."""
    for station_id, terms in aliases.items():
        if any(t and t in q for t in terms):
            return station_id
    return None


def parse(query: str, aliases: dict[str, tuple[str, ...]]) -> ParsedIntent:
    """Classify a rider query into one supported intent + optional station slot (deterministic)."""
    q = query.strip().lower()
    if not q:
        return ParsedIntent("unknown", None)

    station_id = _match_station(q, aliases)
    has = lambda words: any(w in q for w in words)  # noqa: E731 - local readable predicate

    if has(_EVENTS):
        return ParsedIntent("events", station_id)
    if has(_SHORTAGE):
        return ParsedIntent("shortage_warning", station_id)
    if has(_RETURN):
        return ParsedIntent("return_at_location" if station_id else "best_return", station_id)
    if has(_AVAIL):
        return ParsedIntent("best_availability", station_id)
    if station_id is not None:
        return ParsedIntent("status_at_location", station_id)
    if has(_HELP):
        return ParsedIntent("help", None)
    return ParsedIntent("unknown", None)

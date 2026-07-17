"""GraphRAG operator copilot: answer grounded in the as-of event graph. CLAUDE.md §8, §12, §22.

The event graph (Article -> Event -> H3Zone -> Feature -> Forecast) is the *retrieval substrate*:
``build_context`` gathers the as-of events, their grounded evidence, the zones they affect, and the
model-attributed forecast delta — all from the same ReplayEngine artifacts the dashboards use, never
fabricated. When a chat LLM is configured (``LLM_PROVIDER=openai``/``anthropic`` + key) the copilot
asks it to answer *using only that context and citing event ids*; the cited ids are then validated
against the context, so an answer can never reference an event that is not really there. With no key
(the default) it degrades to the deterministic, rule-based :func:`services.api.v2.ops_ask`.

This is GraphRAG, not free generation: the model summarises retrieved, grounded facts — it does not
invent numbers, and it cannot cite an event the graph did not surface.
"""

from __future__ import annotations

import re
from datetime import datetime

from contracts.enums import EffectDirection

from .llm_chat import LlmChatUnavailable, chat, chat_available, chat_provider

_SYSTEM = (
    "You are the operations copilot for a NYC bike-share control tower. Answer the operator's "
    "question USING ONLY the CONTEXT below — a list of currently-known events (each with an id, "
    "grounded evidence, the zones it affects, and the model-attributed forecast change) and the "
    "current system stats. Rules: (1) Every claim must come from the CONTEXT; never invent a "
    "number, "
    "event, or place. (2) Cite the events you use by their id in square brackets, e.g. [evt_ab12]. "
    "(3) If the CONTEXT does not contain the answer, say so plainly. (4) The forecast deltas are "
    "model-attributed, not proven causation — do not claim certainty. (5) Answer in the operator's "
    "language (Korean if they wrote Korean), in 2–4 short sentences. Be concrete and operational."
)

_EVENT_ID_RE = re.compile(r"evt_[0-9a-fA-F]+")


def _effect_ko(effect: EffectDirection) -> str:
    return {
        EffectDirection.INCREASE: "수요 증가",
        EffectDirection.DECREASE: "수요 감소",
    }.get(effect, "영향 불명")


def build_context(engine, cutoff: datetime, *, max_events: int = 12) -> dict:
    """Assemble the grounded, as-of retrieval context for the query (no fabrication)."""
    events = engine.available_events(cutoff)
    forecasts = {zf.zone_id: zf for zf in engine.forecasts(cutoff)}

    # Which zones each event actually reaches, with that zone's model-attributed delta.
    event_cards: list[dict] = []
    for e in events[:max_events]:
        zones: list[dict] = []
        for zf in forecasts.values():
            drivers = engine.drivers(zf.zone_id, cutoff)
            if any(d.event.event_id == e.event_id for d in drivers):
                zones.append({"zone_id": zf.zone_id, "forecast_delta": zf.forecast_delta})
        evidence = e.evidence_spans[0].text if e.evidence_spans else ""
        event_cards.append(
            {
                "event_id": e.event_id,
                "title": e.event_title,
                "type": e.event_type.value,
                "severity": round(float(e.severity), 2),
                "effect": _effect_ko(e.demand_effect),
                "evidence": evidence[:220],
                "zones": zones,
            }
        )
    return {
        "cutoff": cutoff.isoformat(),
        "event_count": len(events),
        "events": event_cards,
    }


def _render_context(ctx: dict, stats: dict) -> str:
    lines = [
        f"AS-OF: {ctx['cutoff']}",
        f"SYSTEM: 가동률 {round(stats['system_utilization'] * 100)}%, "
        f"부족 대여소 {stats['stations_in_shortage']}곳, "
        f"총 부족 {stats['total_shortage_units']}대, 반영 이벤트 {ctx['event_count']}건.",
        "",
        "EVENTS (context — cite by id):",
    ]
    if not ctx["events"]:
        lines.append("  (없음 / none available as-of this cutoff)")
    for c in ctx["events"]:
        zpart = (
            ", ".join(f"{z['zone_id']}(Δ{z['forecast_delta']:+})" for z in c["zones"])
            if c["zones"]
            else "영향 존 없음"
        )
        lines.append(
            f"  [{c['event_id']}] {c['title']} · {c['type']} · {c['effect']} · "
            f"severity {c['severity']} · zones: {zpart}"
        )
        if c["evidence"]:
            lines.append(f"      evidence: \"{c['evidence']}\"")
    return "\n".join(lines)


def graphrag_answer(engine, query: str, cutoff: datetime, stats: dict) -> dict | None:
    """LLM answer grounded in the as-of graph, or ``None`` if chat is unavailable / errors.

    ``stats`` is the already-computed ``operator_statistics`` (passed in to avoid recomputation).
    Returns a dict with the answer, validated citations, and the grounded events used.
    """
    if not chat_available():
        return None
    ctx = build_context(engine, cutoff)
    context_text = _render_context(ctx, stats)
    user = f"CONTEXT:\n{context_text}\n\nQUESTION: {query.strip()}"
    try:
        raw = chat(_SYSTEM, user)
    except (LlmChatUnavailable, Exception):  # noqa: BLE001 - any provider error -> degrade cleanly
        return None
    if not raw:
        return None

    # Validate citations: keep only ids that are really in the context (never a hallucinated event).
    ctx_ids = {c["event_id"] for c in ctx["events"]}
    cited = [eid for eid in dict.fromkeys(_EVENT_ID_RE.findall(raw)) if eid in ctx_ids]
    by_id = {c["event_id"]: c for c in ctx["events"]}
    citations = [{"event_id": eid, "title": by_id[eid]["title"]} for eid in cited]
    return {
        "answer": raw,
        "supported": True,
        "answer_mode": "graphrag_llm",
        "llm_provider": chat_provider(),
        "citations": citations,
        "grounded_event_count": len(ctx["events"]),
        "facts": {"cutoff": ctx["cutoff"], "event_count": ctx["event_count"]},
        "intent": "graphrag",
        "note": (
            f"{chat_provider().upper()} 기반 GraphRAG 응답입니다. 답변은 위 CONTEXT(as-of 이벤트 "
            "그래프·증거·모델 귀속 예측 변화)에서만 생성되며, 인용된 이벤트 id는 실제 그래프에 "
            "존재하는 것만 남깁니다. 예측 변화는 인과가 아닌 모델 귀속치입니다."
        ),
    }

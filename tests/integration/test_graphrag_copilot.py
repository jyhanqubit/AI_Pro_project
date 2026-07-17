"""GraphRAG operator copilot (V2-08). CLAUDE.md §8, §12, §22.

Exercised with an injected fake chat client (no network, no key) so the retrieval assembly, citation
validation, and rule-based degrade are pinned deterministically. The default (mock) path must remain
the deterministic rule-based copilot; the LLM path must never surface an event id that is not in the
grounded context.
"""

from __future__ import annotations

import pytest

from services.api import graphrag, llm_chat, v2
from services.api.replay import DEMO_WINDOW, get_engine


@pytest.fixture
def engine_at_events():
    """Engine with the cutoff advanced so the golden-path events are available."""
    engine = get_engine()
    _, end = DEMO_WINDOW
    engine.set_cutoff(end)
    yield engine
    llm_chat.set_test_client(None)


def test_no_llm_falls_back_to_rule_based(engine_at_events, monkeypatch) -> None:
    monkeypatch.setattr(graphrag, "chat_available", lambda: False)
    r = v2.ops_copilot_answer(engine_at_events, "지금 현황 어때?", engine_at_events.cutoff)
    assert r["answer_mode"] == "rule_based"
    assert r["answer"]  # a deterministic answer is still produced


def test_graphrag_answer_grounds_and_validates_citations(engine_at_events, monkeypatch) -> None:
    engine = engine_at_events
    ev_ids = [e.event_id for e in engine.available_events(engine.cutoff)]
    assert ev_ids, "fixture should expose events at the end of the demo window"

    # Fake GPT cites one REAL event id and one HALLUCINATED id.
    def fake_chat(system: str, user: str) -> str:
        # The grounded context must actually be handed to the model.
        assert ev_ids[0] in user and "CONTEXT" in user
        return f"신호 장애 영향이 큽니다 [{ev_ids[0]}]. 또한 [evt_deadbeef99] 참고."

    monkeypatch.setattr(graphrag, "chat_available", lambda: True)
    monkeypatch.setattr(graphrag, "chat_provider", lambda: "openai")
    llm_chat.set_test_client(fake_chat)

    r = v2.ops_copilot_answer(engine, "무슨 일 있어?", engine.cutoff)
    assert r["answer_mode"] == "graphrag_llm"
    assert r["llm_provider"] == "openai"
    cited = [c["event_id"] for c in r["citations"]]
    assert ev_ids[0] in cited  # real id kept, with its title
    assert "evt_deadbeef99" not in cited  # hallucinated id filtered out (§22)
    assert all(c in ev_ids for c in cited)


def test_graphrag_degrades_when_llm_errors(engine_at_events, monkeypatch) -> None:
    def boom(system: str, user: str) -> str:
        raise RuntimeError("provider 500")

    monkeypatch.setattr(graphrag, "chat_available", lambda: True)
    llm_chat.set_test_client(boom)
    r = v2.ops_copilot_answer(engine_at_events, "지금 현황 어때?", engine_at_events.cutoff)
    # A provider error must degrade to the rule-based answer, never a fabricated one.
    assert r["answer_mode"] == "rule_based"


def test_context_is_grounded_in_real_events(engine_at_events) -> None:
    ctx = graphrag.build_context(engine_at_events, engine_at_events.cutoff)
    ev_ids = {e.event_id for e in engine_at_events.available_events(engine_at_events.cutoff)}
    assert ctx["events"]
    for card in ctx["events"]:
        assert card["event_id"] in ev_ids  # never an invented event
        assert card["evidence"]  # grounded evidence text is present

"""Real OpenAI (GPT-4o) extraction provider (V2, opt-in). CLAUDE.md §8, §22.

The provider is exercised with a **fake injected client** (no network, no key) so the parsing,
grounding, geocoding, clamping, and provenance guarantees are pinned deterministically. The mock
provider remains the Demo-Mode default; this covers only the opt-in real path's contract. Mirrors
``test_anthropic_provider`` — the only difference is the OpenAI chat/tool-call response shape (tool
arguments arrive as a JSON string).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from contracts.article import ArticleRecord
from contracts.enums import ExtractionStatus
from pipelines.events import build_provider, extract_events
from pipelines.events.openai_provider import OpenAiLlmProvider


def _article() -> ArticleRecord:
    ts = datetime(2024, 6, 10, 18, tzinfo=UTC)
    return ArticleRecord(
        article_id="a1",
        title="Signal problems snarl Times Square subway commute",
        text="An MTA service change and signal failure hit Times Square during the evening rush.",
        source="test-wire",
        published_at=ts,
        first_seen_at=ts,
        available_at=ts,
        url_hash="h1",
        mode="research",
        raw_payload_path="none",
    )


def _fake_client(events: list[dict]):
    """A stand-in OpenAI client whose chat.completions.create returns one function tool call.

    OpenAI delivers tool arguments as a JSON **string** (unlike Anthropic's parsed dict), so the
    fake serialises the events the same way the real API would.
    """
    call = SimpleNamespace(
        function=SimpleNamespace(
            name="record_events", arguments=json.dumps({"events": events})
        )
    )
    message = SimpleNamespace(tool_calls=[call])
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    completions = SimpleNamespace(create=lambda **kw: response)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def _provider_with(events: list[dict]) -> OpenAiLlmProvider:
    p = OpenAiLlmProvider(model="gpt-4o")
    p._client = _fake_client(events)  # inject — no SDK/network needed
    return p


def test_builds_grounded_candidate_with_provenance_and_geocode() -> None:
    p = _provider_with(
        [
            {
                "event_type": "TRANSIT_DISRUPTION",
                "event_title": "Times Square signal failure",
                "event_summary": "Signal failure disrupts service.",
                "demand_effect": "increase",
                "capacity_effect": "unknown",
                "severity": 0.7,
                "confidence": 0.8,
                "location_names": ["Times Square"],
                "evidence_quotes": ["signal failure hit Times Square"],
            }
        ]
    )
    [c] = p.extract(_article())
    assert c["event_type"] == "TRANSIT_DISRUPTION"
    assert c["extraction_model"] == "gpt-4o"
    assert c["extraction_prompt_version"] == "openai-extract-v1"
    assert c["evidence_spans"]
    assert c["evidence_spans"][0]["text"] == "signal failure hit Times Square"
    # Deterministic gazetteer geocoding attached a real Times Square coordinate.
    assert any(loc["name"] == "Times Square" for loc in c["locations"])


def test_ungrounded_evidence_drops_the_event() -> None:
    # The quote is not a substring of the article -> no grounded span -> event dropped (§22).
    p = _provider_with(
        [
            {
                "event_type": "WEATHER_SHOCK",
                "event_title": "Storm",
                "event_summary": "A storm.",
                "demand_effect": "decrease",
                "capacity_effect": "unknown",
                "severity": 0.6,
                "confidence": 0.9,
                "location_names": [],
                "evidence_quotes": ["a hurricane made landfall in Brooklyn"],  # not in the text
            }
        ]
    )
    assert p.extract(_article()) == []


def test_severity_and_confidence_are_clamped() -> None:
    p = _provider_with(
        [
            {
                "event_type": "LARGE_VENUE_EVENT",
                "event_title": "Concert",
                "event_summary": "A concert.",
                "demand_effect": "increase",
                "capacity_effect": "decrease",
                "severity": 5.0,  # out of range -> clamp to 1.0
                "confidence": -1.0,  # out of range -> clamp to 0.0
                "location_names": [],
                "evidence_quotes": ["evening rush"],
            }
        ]
    )
    [c] = p.extract(_article())
    assert c["severity"] == 1.0
    assert c["confidence"] == 0.0


def test_unknown_event_type_is_skipped() -> None:
    p = _provider_with(
        [
            {
                "event_type": "ALIEN_INVASION",  # not in the ontology
                "event_title": "x",
                "event_summary": "x",
                "demand_effect": "increase",
                "capacity_effect": "unknown",
                "severity": 0.5,
                "confidence": 0.5,
                "location_names": [],
                "evidence_quotes": ["evening rush"],
            }
        ]
    )
    assert p.extract(_article()) == []


def test_no_tool_call_yields_no_events() -> None:
    p = OpenAiLlmProvider()
    message = SimpleNamespace(tool_calls=None)
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    p._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response))
    )
    assert p.extract(_article()) == []


def test_malformed_arguments_yield_no_events() -> None:
    # A non-JSON arguments payload must not crash — the extractor records it, never fabricates.
    p = OpenAiLlmProvider()
    call = SimpleNamespace(function=SimpleNamespace(name="record_events", arguments="{not json"))
    message = SimpleNamespace(tool_calls=[call])
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    p._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response))
    )
    assert p.extract(_article()) == []


def test_end_to_end_through_extract_events_accepts_and_grounds() -> None:
    # The full extractor validates via Pydantic, grounds evidence, and gates on confidence.
    p = _provider_with(
        [
            {
                "event_type": "TRANSIT_DISRUPTION",
                "event_title": "Times Square signal failure",
                "event_summary": "Signal failure disrupts service.",
                "demand_effect": "increase",
                "capacity_effect": "unknown",
                "severity": 0.7,
                "confidence": 0.8,  # above CONFIDENCE_THRESHOLD -> accepted
                "location_names": ["Times Square"],
                "evidence_quotes": ["signal failure hit Times Square"],
            }
        ]
    )
    events, meta = extract_events([_article()], p)
    assert len(events) == 1
    assert events[0].status is ExtractionStatus.ACCEPTED
    assert events[0].evidence_spans[0].text  # grounded, non-empty
    assert meta.errors == []


def test_build_provider_knows_openai() -> None:
    assert isinstance(build_provider("openai"), OpenAiLlmProvider)
    with pytest.raises(ValueError):
        build_provider("gpt")

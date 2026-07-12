"""Event extraction tests. CLAUDE.md sections 8, 6.3, 17.

Covers deterministic mock output, evidence grounding, confidence-based quarantine, bounded
retry on malformed output (final error recorded), and configurable deduplication.
"""

from __future__ import annotations

from datetime import UTC, datetime

from contracts.article import ArticleRecord
from contracts.enums import EventType, ExtractionStatus, OperatingMode
from pipelines.events import LlmProvider, MockLlmProvider, extract_events

EDT = UTC


def _article(article_id: str, title: str, text: str, hour: int = 14) -> ArticleRecord:
    ts = datetime(2026, 7, 12, hour, 0, tzinfo=EDT)
    return ArticleRecord(
        article_id=article_id,
        title=title,
        text=text,
        source="test",
        published_at=ts,
        first_seen_at=ts,
        url_hash=f"hash_{article_id}",
        mode=OperatingMode.HISTORICAL_REPLAY,
        raw_payload_path="x",
    )


TRANSIT = _article(
    "a2",
    "Signal failure suspends PATH service near Hoboken Terminal",
    "A signal failure has suspended PATH service between Hoboken Terminal and City Hall.",
)
CONCERT = _article(
    "a3",
    "Waterfront concert expected to draw large crowds",
    "A large evening concert at the Newport waterfront is expected to draw thousands.",
)
NEUTRAL = _article("a1", "Quiet morning downtown", "Nothing notable happened today.")


# --- Detection + determinism ----------------------------------------------


def test_transit_disruption_detected_with_demand_increase():
    events, meta = extract_events([TRANSIT], MockLlmProvider())
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type is EventType.TRANSIT_DISRUPTION
    assert ev.demand_effect == "increase"  # transit down -> bikes up
    assert ev.status is ExtractionStatus.ACCEPTED
    assert meta.accepted == 1


def test_no_trigger_yields_no_event():
    events, meta = extract_events([NEUTRAL], MockLlmProvider())
    assert events == []
    assert meta.candidates == 0


def test_mock_is_deterministic():
    a, _ = extract_events([TRANSIT, CONCERT], MockLlmProvider())
    b, _ = extract_events([TRANSIT, CONCERT], MockLlmProvider())
    assert [e.model_dump() for e in a] == [e.model_dump() for e in b]
    assert a[0].event_id == b[0].event_id  # stable ids


def test_evidence_is_grounded_in_article_text():
    events, _ = extract_events([TRANSIT], MockLlmProvider())
    span = events[0].evidence_spans[0]
    assert span.text in TRANSIT.text  # exact substring


# --- Confidence handling (section 8) --------------------------------------


def test_low_confidence_is_quarantined_not_dropped():
    # Raise the threshold above the mock's confidence so the event is quarantined, not erased.
    events, meta = extract_events([CONCERT], MockLlmProvider(), confidence_threshold=0.99)
    assert len(events) == 1
    assert events[0].status is ExtractionStatus.QUARANTINED
    assert meta.quarantined == 1
    assert meta.accepted == 0


# --- Bounded retry (section 8) --------------------------------------------


class _FlakyProvider(LlmProvider):
    """Returns malformed output on the first call, valid output afterwards."""

    model_id = "flaky"

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, article: ArticleRecord) -> list[dict]:
        self.calls += 1
        if self.calls == 1:
            return [{"event_id": "bad"}]  # missing required fields -> ValidationError
        return MockLlmProvider().extract(article)


class _AlwaysBadProvider(LlmProvider):
    model_id = "bad"

    def extract(self, article: ArticleRecord) -> list[dict]:
        return [{"event_id": "bad"}]  # never valid


def test_retry_recovers_from_transient_bad_output():
    provider = _FlakyProvider()
    events, meta = extract_events([TRANSIT], provider, max_retries=2)
    assert provider.calls == 2
    assert len(events) == 1
    assert meta.errors == []


def test_retry_exhausted_records_final_error():
    events, meta = extract_events([TRANSIT], _AlwaysBadProvider(), max_retries=2)
    assert events == []
    assert len(meta.errors) == 1
    assert meta.errors[0][0] == "a2"  # article id recorded


# --- Deduplication (section 8) --------------------------------------------


def test_dedup_merges_near_identical_events():
    dup = _article(
        "a2b",
        "Signal failure suspends PATH service near Hoboken Terminal",  # same title
        "Signal failure has suspended PATH service; single tracking in effect.",
    )
    events, meta = extract_events([TRANSIT, dup], MockLlmProvider(), dedup_threshold=0.6)
    assert len(events) == 1
    assert meta.deduped == 1
    # Provenance from both source articles is preserved after the merge.
    assert set(events[0].source_article_ids) == {"a2", "a2b"}


def test_dedup_keeps_distinct_events():
    events, meta = extract_events([TRANSIT, CONCERT], MockLlmProvider(), dedup_threshold=0.6)
    assert len(events) == 2
    assert meta.deduped == 0

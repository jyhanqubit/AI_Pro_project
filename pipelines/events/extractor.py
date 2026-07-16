"""Event extraction orchestrator. CLAUDE.md sections 8 and 6.3.

Validates provider output with Pydantic (bounded retries), verifies evidence spans are
grounded in the article text, sets accept/quarantine/reject status from confidence, and
deduplicates near-identical events. Rejected/quarantined extractions are kept (auditable),
never silently erased. The final validation error is recorded when extraction fails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from config.events import (
    CONFIDENCE_THRESHOLD,
    DEDUP_JACCARD_THRESHOLD,
    LOW_CONFIDENCE_ACTION,
    MAX_EXTRACTION_RETRIES,
    PROMPT_VERSION,
)
from contracts.article import ArticleRecord
from contracts.enums import ExtractionStatus
from contracts.event import EventExtraction

from .provider import LlmProvider, MockLlmProvider


@dataclass
class ExtractionRunMetadata:
    prompt_version: str = PROMPT_VERSION
    articles: int = 0
    candidates: int = 0
    accepted: int = 0
    quarantined: int = 0
    rejected: int = 0
    deduped: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


def build_provider(name: str) -> LlmProvider:
    """Resolve an extraction provider by name. ``mock`` is the offline default (Demo Mode).

    ``anthropic`` (Claude) and ``openai`` (GPT-4o) are the opt-in real extractors. Each needs its
    own SDK and credentials (``ANTHROPIC_API_KEY`` / an ``ant auth login`` profile for Anthropic;
    ``OPENAI_API_KEY`` or ``openai_api_key`` for OpenAI) and is constructed lazily so this call
    never requires either. A missing SDK/key surfaces only when it actually runs, as a per-article
    extraction error (never a fabricated event).
    """
    if name == "mock":
        return MockLlmProvider()
    if name == "anthropic":
        from .anthropic_provider import AnthropicLlmProvider

        return AnthropicLlmProvider()
    if name == "openai":
        from .openai_provider import OpenAiLlmProvider

        return OpenAiLlmProvider()
    raise ValueError(
        f"unknown LLM provider: {name!r} (available: 'mock', 'anthropic', 'openai')"
    )


def _status_for(confidence: float, threshold: float, low_conf_action: str) -> ExtractionStatus:
    if confidence >= threshold:
        return ExtractionStatus.ACCEPTED
    if low_conf_action == "reject":
        return ExtractionStatus.REJECTED
    return ExtractionStatus.QUARANTINED


def _verify_grounding(article: ArticleRecord, event: EventExtraction) -> None:
    for span in event.evidence_spans:
        if span.text not in article.text and span.text not in article.title:
            raise ValueError(
                f"evidence span not grounded in article {article.article_id}: {span.text!r}"
            )


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _deduplicate(
    events: list[EventExtraction], threshold: float
) -> tuple[list[EventExtraction], int]:
    kept: list[EventExtraction] = []
    removed = 0
    for ev in events:
        ev_tokens = _tokens(ev.event_title)
        for i, existing in enumerate(kept):
            same_type = existing.event_type == ev.event_type
            if same_type and _jaccard(_tokens(existing.event_title), ev_tokens) >= threshold:
                merged_ids = list(
                    dict.fromkeys(existing.source_article_ids + ev.source_article_ids)
                )
                kept[i] = existing.model_copy(
                    update={
                        "source_article_ids": merged_ids,
                        "evidence_spans": existing.evidence_spans + ev.evidence_spans,
                    }
                )
                removed += 1
                break
        else:
            kept.append(ev)
    return kept, removed


def extract_events(
    articles: list[ArticleRecord],
    provider: LlmProvider,
    *,
    max_retries: int = MAX_EXTRACTION_RETRIES,
    dedup_threshold: float = DEDUP_JACCARD_THRESHOLD,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
    low_confidence_action: str = LOW_CONFIDENCE_ACTION,
) -> tuple[list[EventExtraction], ExtractionRunMetadata]:
    meta = ExtractionRunMetadata(articles=len(articles))
    events: list[EventExtraction] = []

    for article in articles:
        last_err: Exception | None = None
        for _attempt in range(max_retries):
            try:
                validated: list[EventExtraction] = []
                for raw in provider.extract(article):
                    candidate = dict(raw)
                    status = _status_for(
                        float(candidate["confidence"]),
                        confidence_threshold,
                        low_confidence_action,
                    )
                    candidate["status"] = status.value
                    event = EventExtraction(**candidate)
                    _verify_grounding(article, event)
                    validated.append(event)
                break  # provider output for this article is valid
            except (ValidationError, ValueError, KeyError) as exc:
                last_err = exc
                validated = []
        else:
            # All retries exhausted: record the final validation error (section 8).
            meta.errors.append((article.article_id, str(last_err)))
            continue

        meta.candidates += len(validated)
        events.extend(validated)

    events, removed = _deduplicate(events, dedup_threshold)
    meta.deduped = removed
    for ev in events:
        if ev.status is ExtractionStatus.ACCEPTED:
            meta.accepted += 1
        elif ev.status is ExtractionStatus.QUARANTINED:
            meta.quarantined += 1
        else:
            meta.rejected += 1

    return events, meta

"""LLM provider interface + deterministic mock. CLAUDE.md section 8.

The provider turns an article into raw structured candidate dicts. The mock is fully
deterministic: same fixture input + same prompt version -> identical output, with no network
and no external key. Real providers implement the same interface later. The extractor (not the
provider) validates output, decides accept/quarantine, and deduplicates.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

from config.events import (
    BASE_SEVERITY,
    EVENT_EFFECT,
    EVENT_KEYWORDS,
    PROMPT_VERSION,
)
from config.places import PLACE_GAZETTEER
from contracts.article import ArticleRecord
from contracts.enums import EventType


def _find_locations(haystack: str) -> list[dict]:
    """Extract known places (deduped by canonical name) mentioned in the text."""
    found: dict[str, dict] = {}
    for phrase, (name, lat, lng) in PLACE_GAZETTEER.items():
        if phrase in haystack and name not in found:
            found[name] = {"name": name, "lat": lat, "lng": lng}
    return list(found.values())


def _stable_event_id(article_id: str, event_type: EventType) -> str:
    raw = f"{article_id}|{event_type.value}|{PROMPT_VERSION}"
    return "evt_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _sentence_around(source: str, idx: int) -> tuple[str, int, int]:
    """Return the sentence containing position ``idx`` plus its char offsets in ``source``."""
    start = source.rfind(".", 0, idx) + 1
    end = source.find(".", idx)
    if end == -1:
        end = len(source)
    sentence = source[start:end].strip()
    # Recompute exact offsets of the stripped substring so it stays grounded in the source.
    lead = source[start:end]
    off = start + (len(lead) - len(lead.lstrip()))
    return sentence, off, off + len(sentence)


def _find_evidence(article: ArticleRecord, phrase: str) -> dict | None:
    """Locate a trigger phrase in the article and return a grounded evidence span dict."""
    for field in (article.text, article.title):
        idx = field.lower().find(phrase)
        if idx >= 0:
            sentence, start, end = _sentence_around(field, idx)
            return {
                "article_id": article.article_id,
                "text": sentence,
                "start_char": start,
                "end_char": end,
            }
    return None


class LlmProvider(ABC):
    """Common extraction-provider interface (section 8)."""

    model_id: str

    @abstractmethod
    def extract(self, article: ArticleRecord) -> list[dict]:
        """Return raw candidate event dicts (without a final ``status``)."""
        raise NotImplementedError


class MockLlmProvider(LlmProvider):
    """Deterministic keyword-based extractor. No network, no key (Demo Mode safe)."""

    model_id = PROMPT_VERSION

    def extract(self, article: ArticleRecord) -> list[dict]:
        haystack = f"{article.title}\n{article.text}".lower()

        # Score each event type by number of distinct trigger hits.
        scored: list[tuple[int, EventType, list[str]]] = []
        for etype, phrases in EVENT_KEYWORDS.items():
            hits = [p for p in phrases if p in haystack]
            if hits:
                scored.append((len(hits), etype, hits))
        if not scored:
            return []  # no event detected (legitimate, not an erasure)

        # Best type: most hits, tie-broken by ontology order for determinism.
        ontology_order = list(EVENT_KEYWORDS)
        scored.sort(key=lambda s: (-s[0], ontology_order.index(s[1])))
        n_hits, etype, hits = scored[0]

        evidence = _find_evidence(article, hits[0])
        if evidence is None:
            return []  # cannot ground the claim -> emit nothing

        demand_effect, capacity_effect = EVENT_EFFECT[etype]
        confidence = min(0.9, 0.4 + 0.15 * n_hits)

        candidate = {
            "event_id": _stable_event_id(article.article_id, etype),
            "source_article_ids": [article.article_id],
            "event_type": etype.value,
            "event_title": article.title,
            "event_summary": article.text[:200],
            "published_at": article.published_at.isoformat(),
            "first_seen_at": article.first_seen_at.isoformat(),
            "event_start_at": article.published_at.isoformat(),
            "locations": _find_locations(haystack),
            "demand_effect": demand_effect.value,
            "capacity_effect": capacity_effect.value,
            "severity": BASE_SEVERITY[etype],
            "confidence": confidence,
            "evidence_spans": [evidence],
            "extraction_model": self.model_id,
            "extraction_prompt_version": PROMPT_VERSION,
        }
        return [candidate]

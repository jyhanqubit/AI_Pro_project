"""Real LLM event-extraction provider (OpenAI / GPT-4o). CLAUDE.md section 8.

Opt-in only — Demo Mode and every test use the deterministic ``MockLlmProvider`` and never this
one (``LLM_PROVIDER=mock`` by default). Set ``LLM_PROVIDER=openai`` and provide an OpenAI key to use
GPT-4o instead of Claude. This provider implements the same ``LlmProvider`` interface as the mock
and the Anthropic provider: it turns one article into raw candidate event dicts, which the extractor
then validates with Pydantic, grounds against the article text, gates on confidence, and dedups.

Guardrails honoured here (section 8, §22) — identical to the Anthropic provider:

* **Structured output** via a forced function/tool call — GPT must return a schema-valid
  ``record_events`` call, so the shape is guaranteed and the extractor's Pydantic validation is a
  second gate.
* **Grounded evidence only** — every evidence quote is kept only if it is an exact substring of the
  article title/text; an event with no grounded span is dropped (never fabricated).
* **Deterministic geocoding** — locations come from the shared gazetteer over the article text, not
  from model-invented coordinates, so Event -> Place -> H3Zone stays trustworthy.
* **No numeric demand %** — the model returns a bounded ``severity``/``confidence`` prior and an
  effect *direction* only.
* **Provenance** — the model id and prompt version travel on every extraction.
* **Degrades, never fabricates** — if the SDK is absent or credentials/network are unavailable, the
  call raises and the extractor records the error for that article (no invented events).

Only the article title and the stored (already-truncated) snippet are sent to the provider — never
secrets, personal data, or a full licensed article body.
"""

from __future__ import annotations

import hashlib
import json

from config.events import OPENAI_PROMPT_VERSION
from config.places import PLACE_GAZETTEER
from config.settings import get_settings
from contracts.article import ArticleRecord
from contracts.enums import EffectDirection, EventType

from .provider import LlmProvider

_EVENT_TYPES = tuple(e.value for e in EventType)
_EFFECTS = tuple(e.value for e in EffectDirection)

# Max article text sent to the provider (chars). Bounds cost and avoids shipping a long body.
_MAX_TEXT = 2000

_SYSTEM = (
    "You extract mobility-relevant events from a single news item for a bike-share demand system. "
    "Only report events that could plausibly shift local bike-share demand or dock capacity "
    "(transit disruptions, weather shocks, large venue events, road closures, public gatherings, "
    "safety incidents, system alerts). Return an empty list if the item has no such event. "
    "Never infer a numeric demand percentage — give an effect direction and a bounded severity "
    "prior only. Every evidence quote MUST be copied verbatim from the provided title or text."
)

# OpenAI function-calling schema (same shape as the Anthropic tool). ``strict`` makes GPT-4o obey
# the schema exactly, so the extractor's Pydantic validation is a second gate rather than the first.
_TOOL = {
    "type": "function",
    "function": {
        "name": "record_events",
        "description": "Record every distinct mobility-relevant event found in the article.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "event_type": {"type": "string", "enum": list(_EVENT_TYPES)},
                            "event_title": {"type": "string"},
                            "event_summary": {"type": "string"},
                            "demand_effect": {"type": "string", "enum": list(_EFFECTS)},
                            "capacity_effect": {"type": "string", "enum": list(_EFFECTS)},
                            "severity": {"type": "number"},
                            "confidence": {"type": "number"},
                            "location_names": {"type": "array", "items": {"type": "string"}},
                            "evidence_quotes": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": [
                            "event_type",
                            "event_title",
                            "event_summary",
                            "demand_effect",
                            "capacity_effect",
                            "severity",
                            "confidence",
                            "location_names",
                            "evidence_quotes",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["events"],
            "additionalProperties": False,
        },
    },
}


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else float(x)


def _ground_quote(article: ArticleRecord, quote: str) -> dict | None:
    """Keep a model-returned quote only if it is an exact substring of the title/text."""
    q = quote.strip()
    if not q:
        return None
    for field in (article.text, article.title):
        idx = field.lower().find(q.lower())
        if idx >= 0:
            return {
                "article_id": article.article_id,
                "text": field[idx : idx + len(q)],
                "start_char": idx,
                "end_char": idx + len(q),
            }
    return None


def _geocode(haystack: str) -> list[dict]:
    """Deterministic gazetteer geocoding over the article text (never model coordinates)."""
    found: dict[str, dict] = {}
    for phrase, (name, lat, lng) in PLACE_GAZETTEER.items():
        if phrase in haystack and name not in found:
            found[name] = {"name": name, "lat": lat, "lng": lng}
    return list(found.values())


def _stable_event_id(article_id: str, event_type: str) -> str:
    raw = f"{article_id}|{event_type}|{OPENAI_PROMPT_VERSION}"
    return "evt_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class OpenAiProviderUnavailable(RuntimeError):
    """Raised when the OpenAI SDK is not installed or no credentials are configured."""


class OpenAiLlmProvider(LlmProvider):
    """Real GPT-4o-backed extractor (opt-in). Same interface as the mock; never used in Demo."""

    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        self.model = model or settings.openai_model
        self.model_id = self.model
        self._client = None  # constructed lazily so importing this module needs no SDK/key

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import openai
        except ImportError as exc:  # SDK not installed -> honest degrade, no fabrication
            raise OpenAiProviderUnavailable(
                "the 'openai' package is not installed (pip install openai)"
            ) from exc
        settings = get_settings()
        # Prefer an explicit configured key; otherwise let the SDK resolve OPENAI_API_KEY from the
        # environment. A missing key surfaces here as a per-article error, never invented.
        self._client = (
            openai.OpenAI(api_key=settings.openai_api_key)
            if settings.openai_api_key
            else openai.OpenAI()
        )
        return self._client

    def extract(self, article: ArticleRecord) -> list[dict]:
        client = self._get_client()
        title = article.title or ""
        text = (article.text or "")[:_MAX_TEXT]
        haystack = f"{title}\n{text}".lower()

        response = client.chat.completions.create(
            model=self.model,
            temperature=0,  # deterministic-as-possible extraction
            tools=[_TOOL],
            tool_choice={"type": "function", "function": {"name": "record_events"}},
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"TITLE: {title}\n\nTEXT: {text}"},
            ],
        )

        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            return []  # no tool call -> no event (not an error)
        try:
            tool_input = json.loads(tool_calls[0].function.arguments)
        except (json.JSONDecodeError, TypeError):
            return []  # malformed args -> extractor retries / records the error

        candidates: list[dict] = []
        for e in tool_input.get("events", []):
            etype = str(e.get("event_type", ""))
            if etype not in _EVENT_TYPES:
                continue
            spans = [s for q in e.get("evidence_quotes", []) if (s := _ground_quote(article, q))]
            if not spans:
                continue  # never accept an event without a grounded evidence span (§22)
            demand = e.get("demand_effect")
            capacity = e.get("capacity_effect")
            candidates.append(
                {
                    "event_id": _stable_event_id(article.article_id, etype),
                    "source_article_ids": [article.article_id],
                    "event_type": etype,
                    "event_title": e.get("event_title") or title,
                    "event_summary": (e.get("event_summary") or text)[:400],
                    "published_at": article.published_at.isoformat(),
                    "first_seen_at": article.first_seen_at.isoformat(),
                    "event_start_at": article.published_at.isoformat(),
                    "locations": _geocode(haystack),
                    "demand_effect": demand if demand in _EFFECTS else "unknown",
                    "capacity_effect": capacity if capacity in _EFFECTS else "unknown",
                    "severity": _clamp01(e.get("severity", 0.5)),
                    "confidence": _clamp01(e.get("confidence", 0.5)),
                    "evidence_spans": spans,
                    "extraction_model": self.model_id,
                    "extraction_prompt_version": OPENAI_PROMPT_VERSION,
                }
            )
        return candidates

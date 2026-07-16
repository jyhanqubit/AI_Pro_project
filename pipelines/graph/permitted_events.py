"""Adapt NYC permitted-events records into graph-ready Event + Article objects. CLAUDE.md §9.

These are **planned, official permit records** (NYC Open Data), not detected news shocks. Each
record is turned into one ``EventExtraction`` (severity is a bounded *prior*, never an observed
causal effect) plus a synthetic ``ArticleRecord`` representing the official record itself. The §9
provenance chain Article -> REPORTS -> Event -> FROM_SOURCE -> Source(``NYC Open Data``) then holds,
so the shared, tested ``upsert_events`` machinery builds the graph unchanged.

Records carry a borough and street text but **no coordinates**, so each event is grounded at its
borough centroid (borough-grain, matching the demand-lift analysis). That is honest and reproducible
— it never invents a precise lat/lng.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from contracts.article import ArticleRecord
from contracts.enums import EffectDirection, EventType, ExtractionStatus, OperatingMode
from contracts.event import EventExtraction

_NYC = ZoneInfo("America/New_York")
_SOURCE = "NYC Open Data - Permitted Events"
_PROMPT_VERSION = "permitted-events-v1"
_MODEL = "nyc-open-data-ingest"

# Borough centroids (same as the demand-lift analysis) — the only spatial anchor these records have.
_BOROUGH_CENTROIDS: dict[str, tuple[float, float]] = {
    "Manhattan": (40.776, -73.971),
    "Brooklyn": (40.650, -73.950),
    "Queens": (40.728, -73.795),
    "Bronx": (40.837, -73.886),
    "Staten Island": (40.579, -74.150),
}

# NYC permit ``event_type`` -> our ontology (contracts.enums.EventType). Bounded severity prior per
# type (crowd-drawing events rank higher). Unmapped types fall through to OTHER / 0.3.
_TYPE_MAP: dict[str, tuple[EventType, float]] = {
    "parade": (EventType.PUBLIC_GATHERING, 0.8),
    "production event": (EventType.LARGE_VENUE_EVENT, 0.6),
    "street event": (EventType.PUBLIC_GATHERING, 0.5),
    "plaza partner event": (EventType.PUBLIC_GATHERING, 0.4),
    "plaza event": (EventType.PUBLIC_GATHERING, 0.4),
    "religious event": (EventType.PUBLIC_GATHERING, 0.4),
    "farmers market": (EventType.PUBLIC_GATHERING, 0.3),
    "open culture": (EventType.PUBLIC_GATHERING, 0.3),
}


def _parse_local(raw: str | None) -> datetime | None:
    """Parse a naive NYC-local timestamp (``2026-06-01T00:00:00.000``) into an aware datetime."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).replace(tzinfo=_NYC)
    except ValueError:
        return None


def _map_type(nyc_type: str, closure: str) -> tuple[EventType, float, EffectDirection]:
    etype, severity = _TYPE_MAP.get(nyc_type.strip().lower(), (EventType.OTHER, 0.3))
    # A lane/street closure removes road & dock-access capacity regardless of the event label.
    capacity = EffectDirection.DECREASE if "closure" in closure.lower() else EffectDirection.UNKNOWN
    return etype, severity, capacity


def _iter_records(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_permitted_as_events(
    path: str | Path, *, limit: int | None = None
) -> tuple[list[EventExtraction], dict[str, ArticleRecord]]:
    """Load permitted-event records into (events, articles_by_id) for ``upsert_events``.

    ``limit`` caps the number of **distinct permits** emitted (None = all). A single permit repeats
    across many date rows (recurring events share one ``event_id``), so duplicate rows are collapsed
    to the first occurrence. Records without a mappable borough or a valid start time are skipped
    (reflected in the shorter output, never fabricated).
    """
    path = Path(path)
    events: list[EventExtraction] = []
    articles: dict[str, ArticleRecord] = {}
    seen_src: set[str] = set()

    for i, rec in enumerate(_iter_records(path)):
        if limit is not None and len(events) >= limit:
            break
        src_id = str(rec.get("event_id") or f"row{i}")
        if src_id in seen_src:
            continue  # same permit, another date row -> one Event only
        borough = str(rec.get("event_borough") or "").strip().title()
        centroid = _BOROUGH_CENTROIDS.get(borough)
        start = _parse_local(rec.get("start_date_time"))
        if centroid is None or start is None:
            continue
        seen_src.add(src_id)
        end = _parse_local(rec.get("end_date_time"))
        if end is not None and end < start:
            end = None  # inconsistent record end -> drop it rather than fail (never fabricate)
        lat, lng = centroid

        name = str(rec.get("event_name") or "Permitted event").strip()
        where = str(rec.get("event_location") or borough).strip()
        etype, severity, capacity = _map_type(
            str(rec.get("event_type") or ""), str(rec.get("street_closure_type") or "")
        )

        # Deterministic id from the source permit id + our prompt version (stable across re-runs).
        event_id = "pevt_" + hashlib.sha256(
            f"{src_id}|{_PROMPT_VERSION}".encode()
        ).hexdigest()[:16]
        article_id = "pdoc_" + hashlib.sha256(src_id.encode()).hexdigest()[:16]

        # The synthetic "article" is the official permit record; its text grounds the evidence span.
        doc_text = f"{name} — {rec.get('event_type', '')} in {borough}. Location: {where}."
        articles[article_id] = ArticleRecord(
            article_id=article_id,
            title=name,
            text=doc_text,
            source=_SOURCE,
            published_at=start,  # the permit is known as of its record date
            first_seen_at=start,
            url_hash=hashlib.sha256(src_id.encode()).hexdigest(),
            mode=OperatingMode.HISTORICAL_REPLAY,
            raw_payload_path=str(path),
        )

        events.append(
            EventExtraction(
                event_id=event_id,
                source_article_ids=[article_id],
                event_type=etype,
                event_title=name,
                event_summary=doc_text,
                published_at=start,
                first_seen_at=start,
                event_start_at=start,
                event_end_at=end,
                locations=[{"name": f"{where} ({borough})", "lat": lat, "lng": lng}],
                demand_effect=EffectDirection.INCREASE,  # a permitted gathering draws local trips
                capacity_effect=capacity,
                severity=severity,
                confidence=0.9,  # authoritative record, not a model guess
                evidence_spans=[
                    {"article_id": article_id, "text": name, "start_char": 0, "end_char": len(name)}
                ],
                extraction_model=_MODEL,
                extraction_prompt_version=_PROMPT_VERSION,
                status=ExtractionStatus.ACCEPTED,
            )
        )

    return events, articles

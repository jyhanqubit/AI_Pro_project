"""Search provider interface + Reciprocal Rank Fusion. CLAUDE.md §12; V2-03.

A ``SearchProvider`` maps a query (with optional geo point + filters) to ranked ``SearchHit``s. The
concrete providers are the offline ``LocalHybridProvider`` (default) and an optional
``ElasticsearchProvider``. ``fuse_rrf`` combines several ranked candidate lists (lexical, vector,
geo) into one list — the fusion the hybrid retriever uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SearchDoc:
    """One indexed document. ``station_id`` / lat / lng are present only for station docs."""

    doc_id: str
    kind: str  # "station" | "help"
    title: str
    text: str  # searchable body (name + aliases + district, or help text)
    station_id: str | None = None
    lat: float | None = None
    lng: float | None = None


@dataclass(frozen=True)
class SearchHit:
    doc_id: str
    kind: str
    title: str
    score: float
    station_id: str | None = None
    lat: float | None = None
    lng: float | None = None
    distance_km: float | None = None
    components: dict[str, float] = field(default_factory=dict)  # per-ranker rank contributions


@runtime_checkable
class SearchProvider(Protocol):
    name: str
    available: bool

    def search(
        self,
        query: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
        k: int = 10,
        kinds: tuple[str, ...] | None = None,
    ) -> list[SearchHit]: ...


def fuse_rrf(
    ranked_lists: dict[str, list[str]], *, k: int = 60, pool: int = 20
) -> dict[str, dict[str, float]]:
    """Reciprocal Rank Fusion over named ranked lists of doc_ids.

    Returns ``{doc_id: {ranker: contribution, ..., "_score": total}}``. Each ranker contributes
    ``1 / (k + rank)`` (rank is 0-based within the top ``pool``); the total is their sum.
    """
    out: dict[str, dict[str, float]] = {}
    for ranker, doc_ids in ranked_lists.items():
        for rank, doc_id in enumerate(doc_ids[:pool]):
            contrib = 1.0 / (k + rank + 1)
            entry = out.setdefault(doc_id, {})
            entry[ranker] = round(contrib, 6)
            entry["_score"] = round(entry.get("_score", 0.0) + contrib, 6)
    return out

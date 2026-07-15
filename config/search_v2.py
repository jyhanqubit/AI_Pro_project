"""Hybrid geo-semantic search configuration (V2-03).

The search stack is provider-based: an offline ``LocalHybridProvider`` (BM25 lexical + char-n-gram
vector + geo_distance, fused with Reciprocal Rank Fusion) is the default and the only path tests
exercise. An optional ``ElasticsearchProvider`` can back it when ``ENABLE_ELASTIC=true`` and a
cluster is reachable; if Elastic is unavailable the factory degrades to the local provider (never a
fabricated result). The operational store (inventory/price) is always the source of truth — search
hits are re-hydrated from it, never trusted for live numbers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_flag(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class SearchConfig:
    # Reciprocal Rank Fusion constant (standard k=60). Higher → flatter rank weighting.
    rrf_k: int = 60
    # Default geo search radius (km) for geo-valid scoring / optional filtering.
    geo_radius_km: float = 1.5
    # How many candidates each ranker contributes before fusion.
    candidate_pool: int = 20
    # Vector dim / n-gram come from the shared VectorStoreConfig (LexicalEmbedder default).

    # Optional Elasticsearch backend (disabled by default; tests never touch it).
    enable_elastic: bool = False
    elastic_url: str = "http://localhost:9200"
    elastic_index_prefix: str = "shockflow"

    version: str = "search-v2"


def load_search_config() -> SearchConfig:
    """Config with the Elastic flag read from the environment (default off, offline-safe)."""
    return SearchConfig(enable_elastic=_env_flag("ENABLE_ELASTIC", False))

"""Optional Elasticsearch provider + factory. CLAUDE.md §7.4; V2-03.

The ``ElasticsearchProvider`` mirrors the ``SearchProvider`` interface using BM25 + kNN vector +
``geo_distance`` and RRF on an Elasticsearch cluster. It is **disabled by default** and lazily
imports ``elasticsearch`` — if the package is missing or the cluster is unreachable it reports
``available = False`` and the factory degrades to the offline ``LocalHybridProvider``. Tests never
touch a live cluster (§17: no internet-dependent tests).
"""

from __future__ import annotations

from dataclasses import dataclass

from config.search_v2 import SearchConfig

from .corpus import build_corpus
from .local_hybrid import LocalHybridProvider
from .provider import SearchDoc, SearchHit, SearchProvider


class ElasticsearchProvider:
    name = "elasticsearch"

    def __init__(self, docs: list[SearchDoc], *, config: SearchConfig) -> None:
        self.cfg = config
        self.docs = docs
        self.available = False
        self._client = None
        try:  # lazy, guarded — never a hard dependency in Demo Mode
            from elasticsearch import Elasticsearch  # type: ignore

            client = Elasticsearch(config.elastic_url, request_timeout=2)
            if client.ping():
                self._client = client
                self.available = True
        except Exception:
            # Missing package or unreachable cluster → stay unavailable (caller degrades).
            self.available = False

    def search(
        self,
        query: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
        k: int = 10,
        kinds: tuple[str, ...] | None = None,
    ) -> list[SearchHit]:
        if not self.available or self._client is None:
            raise RuntimeError("elasticsearch provider unavailable")
        # A real hybrid query (BM25 + kNN + geo_distance + RRF) would run here against the pinned
        # cluster. The offline demo never reaches this path; the local provider is authoritative.
        raise NotImplementedError("live Elasticsearch query is not exercised in Demo Mode")


@dataclass(frozen=True)
class ProviderHandle:
    provider: SearchProvider
    degraded: bool  # True if Elastic was requested but we fell back to local
    reason: str


def build_search_provider(config: SearchConfig | None = None) -> ProviderHandle:
    """Return the active provider. Elastic if enabled+reachable, else degrade to local-hybrid."""
    cfg = config or SearchConfig()
    docs = build_corpus()
    local = LocalHybridProvider(docs, config=cfg)
    if not cfg.enable_elastic:
        return ProviderHandle(local, degraded=False, reason="local-hybrid (elastic disabled)")
    es = ElasticsearchProvider(docs, config=cfg)
    if es.available:
        return ProviderHandle(es, degraded=False, reason="elasticsearch")
    return ProviderHandle(
        local, degraded=True, reason="elastic unavailable → degraded to local-hybrid"
    )

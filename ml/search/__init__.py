"""Hybrid geo-semantic search (V2-03).

Provider-based: an offline ``LocalHybridProvider`` (BM25 + char-n-gram vector + geo, RRF-fused) is
the default and tested path; an optional ``ElasticsearchProvider`` degrades to local when a cluster
is unavailable. See ``config/search_v2.py``.
"""

from .elastic import ElasticsearchProvider, ProviderHandle, build_search_provider
from .local_hybrid import LocalHybridProvider
from .provider import SearchDoc, SearchHit, SearchProvider, fuse_rrf

__all__ = [
    "SearchDoc",
    "SearchHit",
    "SearchProvider",
    "fuse_rrf",
    "LocalHybridProvider",
    "ElasticsearchProvider",
    "ProviderHandle",
    "build_search_provider",
]

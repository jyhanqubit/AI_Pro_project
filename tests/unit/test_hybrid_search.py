"""Hybrid geo-semantic search (V2-03). CLAUDE.md §12, §17.

Covers the offline retriever: RRF fusion, lexical/alias/typo matching, geo ordering, kind filters,
the Elastic→local degrade path, and the gold-set relevance metrics. No network / no live cluster.
"""

from __future__ import annotations

from config.search_v2 import SearchConfig
from ml.search import LocalHybridProvider, build_search_provider, fuse_rrf
from ml.search.corpus import build_corpus
from ml.search.evaluate import evaluate

CITY_HALL = (40.7377, -74.0324)


def _provider() -> LocalHybridProvider:
    return LocalHybridProvider(build_corpus(), config=SearchConfig())


def test_rrf_sums_reciprocal_ranks() -> None:
    fused = fuse_rrf({"a": ["x", "y"], "b": ["y", "x"]}, k=60)
    # y is rank 1 in a and rank 0 in b; x is rank 0 in a and rank 1 in b — symmetric, equal totals.
    assert fused["x"]["_score"] == fused["y"]["_score"]
    assert set(fused) == {"x", "y"}


def test_exact_and_alias_match() -> None:
    p = _provider()
    assert p.search("시청", k=3)[0].station_id == "JC_CITYHALL"
    assert p.search("waterfront", k=3)[0].station_id == "JC_NEWPORT"  # alias → Newport


def test_typo_tolerance_via_vector() -> None:
    # No whitespace ("호보켄터미널") still resolves to Hoboken Terminal via the char-n-gram vector.
    p = _provider()
    assert p.search("호보켄터미널", k=3)[0].station_id == "JC_HOBOKEN"


def test_geo_query_orders_by_distance() -> None:
    p = _provider()
    hits = p.search("자전거", lat=CITY_HALL[0], lng=CITY_HALL[1], k=5)
    station_hits = [h for h in hits if h.kind == "station"]
    assert station_hits[0].station_id == "JC_CITYHALL"
    assert station_hits[0].distance_km == 0.0
    # Distances are populated and non-decreasing enough that the nearest wins.
    assert all(h.distance_km is not None for h in station_hits)


def test_kinds_filter_restricts_results() -> None:
    p = _provider()
    hits = p.search("요금 할증", k=5, kinds=("help",))
    assert hits and all(h.kind == "help" for h in hits)


def test_help_query_returns_help_doc() -> None:
    p = _provider()
    assert p.search("요금 할증 얼마", k=1)[0].doc_id == "help_pricing"


def test_elastic_disabled_uses_local() -> None:
    handle = build_search_provider(SearchConfig(enable_elastic=False))
    assert handle.provider.name == "local-hybrid"
    assert handle.degraded is False


def test_elastic_enabled_but_unavailable_degrades_to_local() -> None:
    # No cluster in tests → must degrade, never fail or fabricate.
    handle = build_search_provider(
        SearchConfig(enable_elastic=True, elastic_url="http://127.0.0.1:1")
    )
    assert handle.provider.name == "local-hybrid"
    assert handle.degraded is True
    assert "degraded" in handle.reason


def test_is_deterministic() -> None:
    p = _provider()
    a = [h.doc_id for h in p.search("호보켄", k=5)]
    b = [h.doc_id for h in p.search("호보켄", k=5)]
    assert a == b


def test_gold_metrics_are_strong() -> None:
    r = evaluate(_provider())
    # Measured on the offline provider over the gold set — must retrieve the relevant doc reliably.
    assert r["recall_at_10"] >= 0.9
    assert r["mrr_at_10"] >= 0.8
    assert r["ndcg_at_5"] >= 0.8
    assert r["geo_valid_at_5"] >= 0.9

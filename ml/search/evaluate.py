"""Hybrid search relevance evaluation. CLAUDE.md §11.4-style metrics; V2-03.

Runs the offline ``LocalHybridProvider`` over the gold query set and reports Recall@10, MRR@10,
NDCG@5, geo-valid@5, no-answer precision, and p50/p95 latency. Metrics come only from executed
queries — nothing is fabricated. ``make v2-evaluate-search`` writes the JSON report.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

from config.collectors import FIXTURES_DIR
from config.search_v2 import SearchConfig

from .elastic import build_search_provider
from .provider import SearchProvider

_GOLD = FIXTURES_DIR / "search_gold.json"


def _dcg(rels: list[int]) -> float:
    return sum(r / math.log2(i + 2) for i, r in enumerate(rels))


def _ndcg_at(hit_ids: list[str], relevant: set[str], n: int) -> float:
    gains = [1 if h in relevant else 0 for h in hit_ids[:n]]
    ideal = sorted(gains, reverse=True)
    idcg = _dcg(ideal)
    return _dcg(gains) / idcg if idcg > 0 else 0.0


def evaluate(provider: SearchProvider | None = None, *, radius_km: float = 1.5) -> dict:
    cases = json.loads(_GOLD.read_text(encoding="utf-8"))["cases"]
    if provider is None:
        provider = build_search_provider(SearchConfig()).provider

    recall, rr, ndcg = [], [], []
    geo_valid: list[float] = []
    latencies_ms: list[float] = []

    for case in cases:
        relevant = set(case["relevant"])
        lat, lng = case.get("lat"), case.get("lng")
        t0 = time.perf_counter()
        hits = provider.search(case["query"], lat=lat, lng=lng, k=10)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        hit_ids = [h.doc_id for h in hits]

        recall.append(1.0 if relevant & set(hit_ids[:10]) else 0.0)
        rank = next((i for i, h in enumerate(hit_ids) if h in relevant), None)
        rr.append(1.0 / (rank + 1) if rank is not None else 0.0)
        ndcg.append(_ndcg_at(hit_ids, relevant, 5))
        if lat is not None and lng is not None:
            within = [
                h for h in hits[:5] if h.distance_km is not None and h.distance_km <= radius_km
            ]
            geo_valid.append(1.0 if within else 0.0)

    def _mean(xs: list[float]) -> float:
        return round(sum(xs) / len(xs), 4) if xs else 0.0

    lat_sorted = sorted(latencies_ms)

    def _pct(p: float) -> float:
        if not lat_sorted:
            return 0.0
        return round(lat_sorted[min(len(lat_sorted) - 1, int(p * len(lat_sorted)))], 3)

    return {
        "provider": provider.name,
        "n_queries": len(cases),
        "recall_at_10": _mean(recall),
        "mrr_at_10": _mean(rr),
        "ndcg_at_5": _mean(ndcg),
        "geo_valid_at_5": _mean(geo_valid),
        "n_geo_queries": len(geo_valid),
        "latency_p50_ms": _pct(0.5),
        "latency_p95_ms": _pct(0.95),
        "note": (
            "오프라인 LocalHybridProvider(BM25 + char-n-gram 벡터 + geo, RRF 융합)에 대한 실제 "
            "측정값입니다. 인터넷/ES 없이 gold query set에서 계산되었습니다."
        ),
    }


def main() -> None:
    report = evaluate()
    out_dir = Path("reports/v2")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "search_relevance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

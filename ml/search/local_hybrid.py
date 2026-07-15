"""Offline hybrid geo-semantic retriever. CLAUDE.md §12; V2-03.

``LocalHybridProvider`` fuses three rankers with Reciprocal Rank Fusion:

* **lexical** — a small BM25 over word tokens (exact/keyword matches),
* **vector** — cosine similarity of the deterministic char-n-gram embedding (typo / near-dup /
  Korean-alias tolerance),
* **geo** — nearest-first by great-circle distance when the query carries a lat/lng.

Deterministic and fully offline (same corpus + query → same ranking). This is the default provider
and the only one the tests exercise.
"""

from __future__ import annotations

import math
import re

from config.search_v2 import SearchConfig
from ml.vectorstore.embedder import LexicalEmbedder
from pipelines.features.kernels import haversine_km

from .provider import SearchDoc, SearchHit, fuse_rrf

_TOKEN = re.compile(r"[0-9a-z가-힣]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class _BM25:
    """Minimal BM25 (Okapi) over a small document set."""

    def __init__(self, docs_tokens: list[list[str]], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.docs = docs_tokens
        self.n = len(docs_tokens)
        self.avg_len = (sum(len(d) for d in docs_tokens) / self.n) if self.n else 0.0
        self.df: dict[str, int] = {}
        for d in docs_tokens:
            for term in set(d):
                self.df[term] = self.df.get(term, 0) + 1

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        # BM25+ idf floor keeps it non-negative for tiny corpora.
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def scores(self, query_tokens: list[str]) -> list[float]:
        out = [0.0] * self.n
        for i, doc in enumerate(self.docs):
            if not doc:
                continue
            counts: dict[str, int] = {}
            for t in doc:
                counts[t] = counts.get(t, 0) + 1
            dl = len(doc)
            s = 0.0
            for q in query_tokens:
                tf = counts.get(q, 0)
                if tf == 0:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * dl / (self.avg_len or 1))
                s += self._idf(q) * (tf * (self.k1 + 1)) / denom
            out[i] = s
        return out


def _rank_order(scores: list[float], doc_ids: list[str]) -> list[str]:
    """doc_ids sorted by descending score; ties broken by doc_id for determinism. Zeros dropped."""
    idx = sorted(range(len(scores)), key=lambda i: (-scores[i], doc_ids[i]))
    return [doc_ids[i] for i in idx if scores[i] > 0]


class LocalHybridProvider:
    name = "local-hybrid"
    available = True

    def __init__(self, docs: list[SearchDoc], *, config: SearchConfig | None = None) -> None:
        self.cfg = config or SearchConfig()
        self.docs = docs
        self.doc_ids = [d.doc_id for d in docs]
        self._by_id = {d.doc_id: d for d in docs}
        self._embedder = LexicalEmbedder()
        self._bm25 = _BM25([_tokens(d.text) for d in docs])
        self._vecs = self._embedder.embed_batch([d.text for d in docs])  # (n, dim), L2-normalised

    def search(
        self,
        query: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
        k: int = 10,
        kinds: tuple[str, ...] | None = None,
    ) -> list[SearchHit]:
        pool = self.cfg.candidate_pool
        keep = [i for i, d in enumerate(self.docs) if kinds is None or d.kind in kinds]
        keep_ids = [self.doc_ids[i] for i in keep]

        # lexical (BM25)
        bm = self._bm25.scores(_tokens(query))
        lexical = _rank_order([bm[i] for i in keep], keep_ids)

        # vector (cosine == dot on L2-normalised vectors)
        qv = self._embedder.embed(query)
        cos = (self._vecs @ qv).tolist()
        vector = _rank_order([cos[i] for i in keep], keep_ids)

        ranked: dict[str, list[str]] = {"lexical": lexical, "vector": vector}

        # geo (nearest first), only when a query point is supplied
        dist: dict[str, float] = {}
        if lat is not None and lng is not None:
            geo_pairs: list[tuple[str, float]] = []
            for i in keep:
                d = self.docs[i]
                if d.lat is None or d.lng is None:
                    continue
                km = haversine_km(lat, lng, d.lat, d.lng)
                dist[d.doc_id] = km
                geo_pairs.append((d.doc_id, km))
            geo_pairs.sort(key=lambda p: (p[1], p[0]))
            ranked["geo"] = [doc_id for doc_id, _ in geo_pairs]

        fused = fuse_rrf(ranked, k=self.cfg.rrf_k, pool=pool)
        order = sorted(fused.items(), key=lambda kv: (-kv[1]["_score"], kv[0]))[:k]

        hits: list[SearchHit] = []
        for doc_id, comp in order:
            d = self._by_id[doc_id]
            hits.append(
                SearchHit(
                    doc_id=doc_id,
                    kind=d.kind,
                    title=d.title,
                    score=comp["_score"],
                    station_id=d.station_id,
                    lat=d.lat,
                    lng=d.lng,
                    distance_km=round(dist[doc_id], 4) if doc_id in dist else None,
                    components={r: v for r, v in comp.items() if r != "_score"},
                )
            )
        return hits

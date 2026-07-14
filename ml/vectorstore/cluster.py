"""Same-event clustering over the news vector store (V1 — accumulating news).

Groups accumulated articles that describe the **same event** by connecting titles whose embeddings
are similar (cosine >= threshold) and taking connected components (union-find). This is a cheap,
deterministic pre-step for event extraction: one cluster -> one candidate event, so the extractor
does not emit N near-identical events from N wire copies of the same story.
"""

from __future__ import annotations

from dataclasses import dataclass

from .news_store import NewsRecord, NewsVectorStore


@dataclass
class NewsCluster:
    cluster_id: int
    article_ids: list[str]
    representative_title: str
    size: int


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def cluster_news(store: NewsVectorStore, threshold: float = 0.3) -> list[NewsCluster]:
    """Connected-component clusters of same-event articles. Deterministic given the store."""
    n = len(store)
    if n == 0:
        return []
    records: list[NewsRecord] = store._records  # noqa: SLF001 (module-internal use)
    vecs = store._index.reconstruct_n(0, n)  # noqa: SLF001
    sims = vecs @ vecs.T

    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            if sims[i, j] >= threshold:
                uf.union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    clusters: list[NewsCluster] = []
    for cid, (_, members) in enumerate(sorted(groups.items())):
        # Representative = the article with the highest intra-cluster similarity (most central).
        best = max(members, key=lambda m: sum(sims[m, o] for o in members))
        clusters.append(
            NewsCluster(
                cluster_id=cid,
                article_ids=sorted(records[m].article_id for m in members),
                representative_title=records[best].title,
                size=len(members),
            )
        )
    # Largest clusters first (the busiest stories).
    return sorted(clusters, key=lambda c: (-c.size, c.cluster_id))

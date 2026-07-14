"""Persistent FAISS news vector store (V1 — accumulating news).

Stores an embedding per news article in a FAISS ``IndexFlatIP`` (cosine over L2-normalised vectors)
plus a metadata sidecar. Designed to **accumulate** across live-collection runs: ``add`` is
idempotent on ``article_id`` and ``save``/``load`` round-trip the index, so repeated real-time
collection keeps growing one store. Supports semantic search and near-duplicate detection (a
stronger dedup than the exact title hash used at ingestion).

FAISS is imported lazily so the base package stays importable without the ``[vectorstore]`` extra.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from config.vectorstore import VectorStoreConfig

from .embedder import LexicalEmbedder


class VectorStoreUnavailable(RuntimeError):
    """Raised when faiss (the [vectorstore] extra) is not installed."""


def _faiss():
    try:
        import faiss  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover
        raise VectorStoreUnavailable(
            "news vector store needs the [vectorstore] extra (pip install -e .[vectorstore])"
        ) from e
    return faiss


@dataclass
class NewsRecord:
    article_id: str
    title: str
    source: str
    published_at: str
    url_hash: str


class NewsVectorStore:
    def __init__(self, config: VectorStoreConfig | None = None) -> None:
        self.cfg = config or VectorStoreConfig()
        self.embedder = LexicalEmbedder(self.cfg)
        self._index = _faiss().IndexFlatIP(self.cfg.dim)
        self._records: list[NewsRecord] = []
        self._ids: set[str] = set()

    def __len__(self) -> int:
        return len(self._records)

    # --- write --------------------------------------------------------------------------------
    def add(self, records: list[NewsRecord]) -> int:
        """Add new articles; skip ids already present or repeated within the batch (idempotent)."""
        fresh: list[NewsRecord] = []
        seen = set(self._ids)
        for r in records:
            if r.article_id in seen:
                continue
            seen.add(r.article_id)
            fresh.append(r)
        if not fresh:
            return 0
        vecs = self.embedder.embed_batch([r.title for r in fresh])
        self._index.add(vecs)
        for r in fresh:
            self._records.append(r)
            self._ids.add(r.article_id)
        return len(fresh)

    # --- read ---------------------------------------------------------------------------------
    def search(self, query: str, k: int = 5) -> list[tuple[NewsRecord, float]]:
        if len(self) == 0:
            return []
        q = self.embedder.embed(query).reshape(1, -1)
        scores, idx = self._index.search(q, min(k, len(self)))
        pairs = zip(scores[0], idx[0], strict=True)
        return [(self._records[int(i)], float(s)) for s, i in pairs if i >= 0]

    def near_duplicates(self, threshold: float | None = None) -> list[tuple[str, str, float]]:
        """Article-id pairs whose titles are near-identical (cosine >= threshold)."""
        thr = self.cfg.dedup_threshold if threshold is None else threshold
        if len(self) < 2:
            return []
        vecs = self._index.reconstruct_n(0, len(self))
        sims = vecs @ vecs.T
        out: list[tuple[str, str, float]] = []
        for i in range(len(self)):
            for j in range(i + 1, len(self)):
                if sims[i, j] >= thr:
                    out.append((self._records[i].article_id, self._records[j].article_id,
                                float(sims[i, j])))
        return out

    # --- persistence (accumulates across runs) ------------------------------------------------
    def save(self, directory: str | Path | None = None) -> Path:
        d = Path(directory or self.cfg.store_dir)
        d.mkdir(parents=True, exist_ok=True)
        _faiss().write_index(self._index, str(d / "index.faiss"))
        (d / "meta.json").write_text(
            json.dumps(
                {"dim": self.cfg.dim, "records": [asdict(r) for r in self._records]},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        return d

    @classmethod
    def load(
        cls, directory: str | Path, config: VectorStoreConfig | None = None
    ) -> NewsVectorStore:
        d = Path(directory)
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        cfg = config or VectorStoreConfig(dim=int(meta["dim"]))
        store = cls.__new__(cls)
        store.cfg = cfg
        store.embedder = LexicalEmbedder(cfg)
        store._index = _faiss().read_index(str(d / "index.faiss"))
        store._records = [NewsRecord(**r) for r in meta["records"]]
        store._ids = {r.article_id for r in store._records}
        return store

    @classmethod
    def load_or_new(
        cls, directory: str | Path, config: VectorStoreConfig | None = None
    ) -> NewsVectorStore:
        d = Path(directory)
        if (d / "index.faiss").exists() and (d / "meta.json").exists():
            return cls.load(d, config)
        return cls(config)

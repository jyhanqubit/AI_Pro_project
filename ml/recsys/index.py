"""Dense retrieval indexes (V1_Prompt §14).

ExactTorchIndex is the required default: a brute-force dot-product Top-K over station embeddings —
by construction it *is* the exact score, so it must match a manual brute force (acceptance test).
The cache key binds an index to its cutoff + model/feature/event-feature versions + station-snapshot
hash, so a stale index is never reused after any of those change.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import torch
from torch import Tensor


@dataclass(frozen=True)
class IndexKey:
    cutoff: str
    model_version: str
    feature_version: str
    event_feature_version: str
    station_snapshot_hash: str

    def fingerprint(self) -> str:
        raw = "|".join(
            [self.cutoff, self.model_version, self.feature_version,
             self.event_feature_version, self.station_snapshot_hash]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def station_snapshot_hash(station_ids: list[str], embeddings: Tensor) -> str:
    h = hashlib.sha256()
    h.update("".join(station_ids).encode("utf-8"))
    h.update(embeddings.detach().cpu().numpy().tobytes())
    return h.hexdigest()[:16]


class ExactTorchIndex:
    """Brute-force exact dot-product retrieval. Required default (no FAISS dependency)."""

    def __init__(self, station_ids: list[str], embeddings: Tensor, key: IndexKey) -> None:
        if embeddings.shape[0] != len(station_ids):
            raise ValueError("embeddings/station_ids length mismatch")
        self.station_ids = station_ids
        self._emb = embeddings.detach()
        self.key = key

    def is_stale(self, key: IndexKey) -> bool:
        """True if this index must be rebuilt for ``key`` (any binding field changed)."""
        return self.key.fingerprint() != key.fingerprint()

    def search(self, query: Tensor, k: int) -> tuple[Tensor, Tensor]:
        """Return (scores, indices) of the Top-k stations per query row."""
        scores = query @ self._emb.T  # (Q, N) exact dot product
        k = min(k, scores.shape[1])
        top = torch.topk(scores, k=k, dim=1)
        return top.values, top.indices

    def ids_for(self, indices: Tensor) -> list[list[str]]:
        return [[self.station_ids[int(j)] for j in row] for row in indices]


def try_build_faiss_index(station_ids: list[str], embeddings: Tensor):
    """Optional FAISS index (§14). Returns None when faiss is not installed (documented skip)."""
    try:
        import faiss  # type: ignore
    except ImportError:
        return None
    import numpy as np

    mat = embeddings.detach().cpu().numpy().astype("float32")
    index = faiss.IndexFlatIP(mat.shape[1])
    index.add(mat)
    return index, station_ids, np  # caller uses index.search

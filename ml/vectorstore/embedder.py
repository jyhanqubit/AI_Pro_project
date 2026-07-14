"""Deterministic offline text embedder (V1 vector store).

Char-n-gram **feature hashing** into a fixed dense vector, L2-normalised. No training and no
external model download, so it runs offline and is fully reproducible (same text -> same vector).
It captures lexical/near-duplicate similarity of short news titles well; a neural embedder can
replace it later without changing the store interface.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np

from config.vectorstore import VectorStoreConfig

_NON_ALNUM = re.compile(r"[^0-9a-z가-힣]+")


def _normalise(text: str) -> str:
    return _NON_ALNUM.sub(" ", text.lower()).strip()


class LexicalEmbedder:
    def __init__(self, config: VectorStoreConfig | None = None) -> None:
        self.cfg = config or VectorStoreConfig()

    def _ngrams(self, text: str) -> list[str]:
        t = f" {_normalise(text)} "
        grams: list[str] = []
        for n in range(self.cfg.ngram_min, self.cfg.ngram_max + 1):
            grams += [t[i : i + n] for i in range(len(t) - n + 1)]
        return grams or [text[: self.cfg.ngram_min] or "_"]

    def embed(self, text: str) -> np.ndarray:
        dim = self.cfg.dim
        vec = np.zeros(dim, dtype=np.float32)
        for g in self._ngrams(text):
            d = hashlib.blake2b(g.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(d[:4], "big") % dim
            sign = 1.0 if (d[4] & 1) else -1.0
            vec[idx] += sign
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 0 else vec

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.cfg.dim), dtype=np.float32)
        return np.vstack([self.embed(t) for t in texts]).astype(np.float32)

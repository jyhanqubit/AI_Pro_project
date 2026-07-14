"""Vector-store configuration (FAISS).

A persistent FAISS index for accumulating news + the recsys FaissIndex. The default text embedder is
a deterministic **offline lexical** embedder (char-n-gram feature hashing) — no external model
download (keeps tests/Demo offline). A neural embedder can be swapped in when online.
"""

from __future__ import annotations

from dataclasses import dataclass

VECTORSTORE_CONFIG_VERSION = "vectorstore-v1"


@dataclass(frozen=True)
class VectorStoreConfig:
    dim: int = 256  # embedding dimensionality (feature-hashing space)
    ngram_min: int = 3  # char n-gram range for the lexical embedder
    ngram_max: int = 5
    dedup_threshold: float = 0.92  # cosine >= this => near-duplicate news title
    store_dir: str = "data/processed/vectorstore/news"  # persistent, accumulates across runs
    version: str = VECTORSTORE_CONFIG_VERSION

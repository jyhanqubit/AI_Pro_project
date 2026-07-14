"""FAISS vector store: accumulating news embeddings + a persistent ANN index.

Offline & deterministic by default (a lexical char-n-gram embedder — no external model download).
FAISS is an optional extra; import lazily so the base install works without it.
"""

from __future__ import annotations

from .embedder import LexicalEmbedder
from .news_store import NewsRecord, NewsVectorStore

__all__ = ["LexicalEmbedder", "NewsRecord", "NewsVectorStore"]

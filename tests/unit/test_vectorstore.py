"""FAISS vector-store tests. Skipped when the [vectorstore] extra (faiss) is absent."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("faiss")  # offline-safe: base install has no faiss

from config.vectorstore import VectorStoreConfig  # noqa: E402
from ml.vectorstore import LexicalEmbedder, NewsRecord, NewsVectorStore  # noqa: E402


def _rec(i: int, title: str) -> NewsRecord:
    return NewsRecord(article_id=f"n{i}", title=title, source="wire",
                      published_at="2026-06-12T00:00:00+00:00", url_hash=f"h{i}")


def test_embedder_is_deterministic_and_normalised() -> None:
    emb = LexicalEmbedder()
    a = emb.embed("PATH signal failure at Hoboken")
    b = emb.embed("PATH signal failure at Hoboken")
    assert np.allclose(a, b)  # deterministic
    assert abs(np.linalg.norm(a) - 1.0) < 1e-5  # L2-normalised


def test_add_search_and_batch_dedup() -> None:
    store = NewsVectorStore()
    added = store.add([
        _rec(1, "Signal failure suspends PATH service near Hoboken Terminal"),
        _rec(2, "Waterfront concert expected to draw large crowds in Newport"),
        _rec(1, "Signal failure suspends PATH service near Hoboken Terminal"),  # dup id in batch
    ])
    assert added == 2 and len(store) == 2  # within-batch duplicate id skipped
    hits = store.search("PATH suspended Hoboken", k=2)
    assert hits and hits[0][0].article_id == "n1"  # nearest is the PATH article


def test_idempotent_accumulation() -> None:
    store = NewsVectorStore()
    recs = [_rec(1, "NJ Transit delays on the Hoboken line"), _rec(2, "Jersey City street closure")]
    assert store.add(recs) == 2
    assert store.add(recs) == 0  # re-adding the same ids grows the store by 0
    assert len(store) == 2


def test_near_duplicate_detection() -> None:
    store = NewsVectorStore(VectorStoreConfig(dedup_threshold=0.9))
    store.add([
        _rec(1, "PATH service suspended near Hoboken Terminal today"),
        _rec(2, "PATH service suspended near Hoboken Terminal today!"),  # near-identical
        _rec(3, "Completely unrelated Jersey City budget vote"),
    ])
    dups = store.near_duplicates()
    pair_ids = {frozenset((a, b)) for a, b, _ in dups}
    assert frozenset(("n1", "n2")) in pair_ids
    assert frozenset(("n1", "n3")) not in pair_ids


def test_persist_and_reload_accumulates(tmp_path: Path) -> None:
    d = tmp_path / "store"
    s1 = NewsVectorStore()
    s1.add([_rec(1, "PATH delay at Grove Street"), _rec(2, "Newport concert tonight")])
    s1.save(d)
    s2 = NewsVectorStore.load(d)
    assert len(s2) == 2
    # A later collection run adds only genuinely new items.
    assert s2.add([_rec(2, "Newport concert tonight"), _rec(3, "Journal Square festival")]) == 1
    assert len(s2) == 3
    assert s2.search("Grove Street PATH", k=1)[0][0].article_id == "n1"


def test_recsys_faiss_index_matches_exact_torch_index() -> None:
    """The optional FaissIndex (IndexFlatIP) must return the same Top-K as ExactTorchIndex."""
    import torch

    from ml.recsys.index import ExactTorchIndex, FaissIndex, IndexKey, station_snapshot_hash

    torch.manual_seed(0)
    emb = torch.nn.functional.normalize(torch.randn(30, 16), dim=-1)
    ids = [f"s{i}" for i in range(30)]
    key = IndexKey("c", "m", "f", "e", station_snapshot_hash(ids, emb))
    q = torch.nn.functional.normalize(torch.randn(4, 16), dim=-1)

    ex_scores, ex_idx = ExactTorchIndex(ids, emb, key).search(q, k=10)
    fa_scores, fa_idx = FaissIndex(ids, emb, key).search(q, k=10)
    assert torch.equal(ex_idx, fa_idx)  # identical ranking
    assert torch.allclose(ex_scores, fa_scores, atol=1e-4)

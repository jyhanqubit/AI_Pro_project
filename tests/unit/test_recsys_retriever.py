"""V1-07B ShockFlowRecFormerRetriever tests — §14 acceptance criteria.

- ExactTorchIndex matches a manual brute force.
- Masks are actually applied in attention (padded events / missing optional features are ignored).
- Same checkpoint + input -> same score (determinism).
- A stale index (changed version/cutoff/snapshot) is detected.
- InfoNCE trains; train+eval runs and records insufficient_event_overlap on plain trip data.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import torch

from config.recsys import RetrieverConfig
from ml.recsys import build_dataset, build_station_master
from ml.recsys.encoder import ShockFlowRecFormerRetriever
from ml.recsys.index import ExactTorchIndex, IndexKey, station_snapshot_hash
from ml.recsys.retriever import build_index, evaluate_retriever, train_retriever
from ml.recsys.tokenize import RetrieverTokenizer

_ROOT = Path(__file__).resolve().parents[2]
_TRIPS = _ROOT / "data" / "fixtures" / "citibike_sample.csv"
_GBFS = _ROOT / "data" / "fixtures" / "gbfs_station_status.json"


def _tiny_cfg() -> RetrieverConfig:
    return RetrieverConfig(
        d_model=32, embedding_dim=32, nhead=4, num_layers=1, dim_feedforward=64,
        dropout=0.0, epochs=1, batch_size=8, max_train_samples=12, hard_negatives=2, seed=0,
    )


@pytest.fixture
def master():
    return build_station_master(pd.read_csv(_TRIPS), gbfs_status_path=_GBFS)


@pytest.fixture
def samples():
    return build_dataset(pd.read_csv(_TRIPS))


def _model_tok(master, cfg):
    torch.manual_seed(cfg.seed)
    tok = RetrieverTokenizer(master, cfg)
    model = ShockFlowRecFormerRetriever(cfg, num_stations=tok.num_stations).eval()
    return model, tok


def test_exact_index_matches_bruteforce() -> None:
    torch.manual_seed(0)
    emb = torch.nn.functional.normalize(torch.randn(20, 16), dim=-1)
    q = torch.nn.functional.normalize(torch.randn(5, 16), dim=-1)
    key = IndexKey("c", "m", "f", "e", station_snapshot_hash([str(i) for i in range(20)], emb))
    idx = ExactTorchIndex([str(i) for i in range(20)], emb, key)
    scores, indices = idx.search(q, k=10)
    brute = q @ emb.T
    b_scores, b_idx = torch.topk(brute, k=10, dim=1)
    assert torch.allclose(scores, b_scores, atol=1e-5)
    assert torch.equal(indices, b_idx)


def test_index_staleness_on_version_change() -> None:
    emb = torch.nn.functional.normalize(torch.randn(4, 8), dim=-1)
    ids = ["a", "b", "c", "d"]
    base = IndexKey("2026-06-01", "m1", "f1", "e1", station_snapshot_hash(ids, emb))
    idx = ExactTorchIndex(ids, emb, base)
    assert not idx.is_stale(base)
    assert idx.is_stale(IndexKey("2026-06-02", "m1", "f1", "e1", base.station_snapshot_hash))
    assert idx.is_stale(IndexKey("2026-06-01", "m2", "f1", "e1", base.station_snapshot_hash))
    assert idx.is_stale(IndexKey("2026-06-01", "m1", "f1", "e1", "deadbeefdeadbeef"))


def test_padding_mask_ignores_absent_events(master, samples) -> None:
    model, tok = _model_tok(master, _tiny_cfg())
    batch = tok.query_batch(samples[:4])
    with torch.no_grad():
        base = model.query_embed(**batch)
    # Events are all absent (present=False). Corrupting their features must not change the output.
    batch["event_feats"] = torch.randn_like(batch["event_feats"])  # type: ignore[index]
    with torch.no_grad():
        after = model.query_embed(**batch)
    assert torch.allclose(base, after, atol=1e-6)


def test_missing_embedding_ignores_absent_optional_features(master, samples) -> None:
    model, tok = _model_tok(master, _tiny_cfg())
    batch = tok.query_batch(samples[:4])
    with torch.no_grad():
        base = model.query_embed(**batch)
    # FORECAST is absent -> replaced by the learned missing embedding; raw values are irrelevant.
    feats = batch["scalar_feats"]  # type: ignore[index]
    feats["FORECAST"] = torch.randn_like(feats["FORECAST"])
    with torch.no_grad():
        after = model.query_embed(**batch)
    assert torch.allclose(base, after, atol=1e-6)


def test_deterministic_scores_same_seed(master, samples) -> None:
    cfg = _tiny_cfg()
    m1, t1 = _model_tok(master, cfg)
    m2, t2 = _model_tok(master, cfg)
    b1 = t1.query_batch(samples[:4])
    b2 = t2.query_batch(samples[:4])
    with torch.no_grad():
        assert torch.allclose(m1.query_embed(**b1), m2.query_embed(**b2), atol=1e-6)


def test_info_nce_backward(master, samples) -> None:
    cfg = _tiny_cfg()
    model, tok = _model_tok(master, cfg)
    model.train()
    q = model.query_embed(**tok.query_batch(samples[:4]))
    pos_stations = [master.get(s.chosen_station_id) for s in samples[:4]]
    s_pos = model.station_embed(**tok.station_batch(pos_stations))
    loss = model.info_nce(q, s_pos, s_neg=None)
    loss.backward()
    assert torch.isfinite(loss)
    assert any(p.grad is not None for p in model.parameters())


def test_train_and_evaluate_smoke(master, samples) -> None:
    cfg = _tiny_cfg()
    model, tok = train_retriever(samples, master, cfg)
    index = build_index(model, master, tok, cutoff="2026-06-30T00:00:00-04:00")
    assert not index.is_stale(index.key)
    train_chosen = {s.chosen_station_id for s in samples}
    rep = evaluate_retriever(model, index, samples, master, tok, train_chosen, cfg)
    assert rep.n == len(samples)
    for v in (rep.recall_at_5, rep.recall_at_20, rep.mrr_at_20, rep.ndcg_at_20):
        assert 0.0 <= v <= 1.0
    assert rep.recall_at_5 <= rep.recall_at_20
    assert rep.event_status == "insufficient_event_overlap"  # no events on plain trip data

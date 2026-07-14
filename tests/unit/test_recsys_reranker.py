"""V1-07C reranker + policy + serving tests (V1_Prompt §15 acceptance)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
import torch

from config.recsys import RetrieverConfig
from contracts.v1.enums import ReasonCode, RecommendationMode
from contracts.v1.recommendation import RecommendationResult
from ml.recsys import build_station_master
from ml.recsys.encoder import ShockFlowRecFormerRetriever
from ml.recsys.policy import PolicyConfig, RerankedCandidate, apply_policy
from ml.recsys.reranker import (
    N_PAIR,
    ShockFlowRecFormerReranker,
    listwise_loss,
    pairwise_loss,
)
from ml.recsys.retriever import build_index
from ml.recsys.serving import RecommendationEngine, query_from_request
from ml.recsys.tokenize import RetrieverTokenizer

_ROOT = Path(__file__).resolve().parents[2]
_TRIPS = _ROOT / "data" / "fixtures" / "citibike_sample.csv"
_GBFS = _ROOT / "data" / "fixtures" / "gbfs_station_status.json"
TZ = timezone(timedelta(hours=-4))
CUTOFF = datetime(2026, 6, 30, 14, 0, tzinfo=TZ)


def _cfg() -> RetrieverConfig:
    return RetrieverConfig(
        d_model=32, embedding_dim=32, nhead=4, num_layers=1, dim_feedforward=64,
        dropout=0.0, retrieval_top_k=10, seed=0,
    )


@pytest.fixture
def master():
    return build_station_master(pd.read_csv(_TRIPS), gbfs_status_path=_GBFS)


def test_reranker_forward_and_losses() -> None:
    torch.manual_seed(0)
    cfg = _cfg()
    rr = ShockFlowRecFormerReranker(cfg)
    p = 5
    q = torch.randn(p, cfg.embedding_dim)
    s = torch.randn(p, cfg.embedding_dim)
    pf = torch.randn(p, N_PAIR)
    logits = rr(q, s, pf)
    assert logits.shape == (p,)
    lw = listwise_loss(logits, positive_idx=2)
    lw.backward()
    assert torch.isfinite(lw)
    pw = pairwise_loss(logits.detach(), positive_idx=2)
    assert pw >= 0


def _cand(sid: str, detour: float, fresh: bool, op: float, rerank: float, prob: float):
    return RerankedCandidate(
        station_id=sid, mode=RecommendationMode.RENT, distance_km=0.3, detour_km=detour,
        retrieval_score=1.0, rerank_score=rerank, success_component=prob,
        operational_component=op, inventory_fresh=fresh,
    )


def test_policy_no_feasible_candidate() -> None:
    res = apply_policy(
        "r1", RecommendationMode.RENT, CUTOFF, [], "ret", "rr",
    )
    assert res.no_feasible_candidate is True
    assert res.stations == []


def test_policy_ranks_and_keeps_components_and_reason_codes() -> None:
    feasible = [
        _cand("A", detour=0.1, fresh=True, op=0.9, rerank=2.0, prob=0.7),
        _cand("B", detour=1.0, fresh=False, op=0.0, rerank=0.5, prob=0.2),
        _cand("C", detour=0.05, fresh=True, op=0.6, rerank=1.0, prob=0.1),
    ]
    res = apply_policy("r1", RecommendationMode.RENT, CUTOFF, feasible, "ret-v1", "rr-v1",
                       PolicyConfig(top_k=3))
    assert not res.no_feasible_candidate
    assert [s.rank for s in res.stations] == [1, 2, 3]
    top = res.stations[0]
    # Components are kept separate (audit).
    for attr in ("retrieval_score", "rerank_score", "success_component",
                 "operational_component", "detour_component", "final_policy_score"):
        assert getattr(top, attr) is not None
    assert top.station_id == "A"  # highest final policy score
    assert ReasonCode.HIGH_SUCCESS_PROBABILITY in top.reason_codes
    assert ReasonCode.LOW_DETOUR in top.reason_codes
    # Stale-inventory candidate flags it.
    b = next(s for s in res.stations if s.station_id == "B")
    assert b.inventory_is_stale and ReasonCode.INVENTORY_STALE in b.reason_codes


def _engine(master) -> RecommendationEngine:
    cfg = _cfg()
    torch.manual_seed(0)
    tok = RetrieverTokenizer(master, cfg)
    retriever = ShockFlowRecFormerRetriever(cfg, num_stations=tok.num_stations)
    reranker = ShockFlowRecFormerReranker(cfg)
    index = build_index(retriever, master, tok, cutoff=CUTOFF.isoformat())
    return RecommendationEngine(retriever, reranker, index, master, tok, cfg, PolicyConfig(top_k=3))


def test_serving_returns_valid_feasible_topk(master) -> None:
    engine = _engine(master)
    q = query_from_request(RecommendationMode.RENT, 40.7196, -74.0431, CUTOFF)
    res, failures = engine.recommend(q, "req1")
    assert isinstance(res, RecommendationResult)
    if not res.no_feasible_candidate:
        assert 1 <= len(res.stations) <= 3
        assert all(s.feasible for s in res.stations)
        # RENT with GBFS: a zero-bike station must never be surfaced (removed, not penalised).
        assert "HB102" not in [s.station_id for s in res.stations]  # HB102 has 0 bikes
    assert isinstance(failures, list)


def test_compare_event_impact_no_overlap(master) -> None:
    engine = _engine(master)
    q = query_from_request(RecommendationMode.RENT, 40.7196, -74.0431, CUTOFF)
    cmp = engine.compare_event_impact(q, "req2", events=None)
    assert cmp["event_status"] == "insufficient_event_overlap"
    assert cmp["event_off_top3"] == cmp["event_on_top3"]  # no events -> identical
    assert cmp["top3_overlap"] == len(cmp["event_off_top3"])

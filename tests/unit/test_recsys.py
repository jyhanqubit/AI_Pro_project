"""V1-07A recommendation dataset/candidate/baseline tests (V1_Prompt §13 acceptance)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from config.recsys import RecsysConfig
from contracts.v1.enums import RecommendationMode
from ml.recsys import (
    build_dataset,
    build_station_master,
    chronological_split,
    generate_candidates,
)
from ml.recsys.baselines import b0_nearest_feasible, b1_distance_capacity, b2_distance_risk_benefit
from ml.recsys.metrics import evaluate
from ml.recsys.mlp import MlpPairScorer

_ROOT = Path(__file__).resolve().parents[2]
_TRIPS = _ROOT / "data" / "fixtures" / "citibike_sample.csv"
_GBFS = _ROOT / "data" / "fixtures" / "gbfs_station_status.json"


@pytest.fixture
def trips() -> pd.DataFrame:
    return pd.read_csv(_TRIPS)


@pytest.fixture
def master(trips: pd.DataFrame):
    return build_station_master(trips, gbfs_status_path=_GBFS)


def test_station_master_has_zone_and_inventory_mask(trips: pd.DataFrame, master) -> None:
    assert len(master) >= 4
    for st in master.all():
        assert st.zone_id  # H3 zone assigned
        # inventory_known is a mask, never fabricated
        assert isinstance(st.inventory_known, bool)


def test_dataset_is_deterministic(trips: pd.DataFrame) -> None:
    a = build_dataset(trips, RecsysConfig())
    b = build_dataset(trips, RecsysConfig())
    assert [s.sample_id for s in a] == [s.sample_id for s in b]
    assert [(s.query_lat, s.query_lng) for s in a] == [(s.query_lat, s.query_lng) for s in b]


def test_query_features_do_not_leak_chosen_station(trips: pd.DataFrame) -> None:
    for s in build_dataset(trips, RecsysConfig()):
        feats = s.query_features()
        assert "chosen_station_id" not in feats
        # No feature value equals/encodes the label station id.
        assert all(isinstance(v, float) for v in feats.values())
        assert s.chosen_station_id  # label exists, but off the query side


def test_query_is_synthetic_flagged(trips: pd.DataFrame) -> None:
    for s in build_dataset(trips, RecsysConfig()):
        assert s.query_is_synthetic is True
        assert s.label_source == "historical_choice_with_synthetic_query"


def test_chronological_split_no_future_leak(trips: pd.DataFrame) -> None:
    samples = build_dataset(trips, RecsysConfig())
    train, test = chronological_split(samples, test_fraction=0.3)
    assert train and test
    assert max(s.cutoff for s in train) <= min(s.cutoff for s in test)


def test_positive_in_candidate_and_rent_return(trips: pd.DataFrame, master) -> None:
    samples = build_dataset(trips, RecsysConfig())
    modes = {s.mode for s in samples}
    assert modes == {RecommendationMode.RENT, RecommendationMode.RETURN}
    for s in samples:
        cands = generate_candidates(s, master, RecsysConfig())
        assert any(c.is_positive for c in cands)  # chosen always reachable


def test_baselines_rank_and_feasible_first(trips: pd.DataFrame, master) -> None:
    cfg = RecsysConfig()
    for ranker in (b0_nearest_feasible, b1_distance_capacity, b2_distance_risk_benefit):
        for s in build_dataset(trips, cfg):
            cands = generate_candidates(s, master, cfg)
            ranked = ranker(s, cands, master)
            assert set(ranked) == {c.station_id for c in cands}  # a permutation
            feas = [c.station_id for c in cands if c.feasible]
            infeas = [c.station_id for c in cands if not c.feasible]
            if feas and infeas:
                last_feasible = max(ranked.index(x) for x in feas)
                first_infeasible = min(ranked.index(x) for x in infeas)
                assert last_feasible < first_infeasible  # feasible outrank infeasible


def test_metrics_in_range(trips: pd.DataFrame, master) -> None:
    cfg = RecsysConfig()
    cases = []
    for s in build_dataset(trips, cfg):
        cands = generate_candidates(s, master, cfg)
        ranked = b0_nearest_feasible(s, cands, master)
        cases.append((cands, ranked, s.chosen_station_id))
    rep = evaluate(cases)
    assert rep.n == len(cases)
    for v in (rep.hit_rate_at_1, rep.hit_rate_at_3, rep.mrr, rep.ndcg_at_3,
              rep.positive_in_candidate_rate, rep.inventory_missing_rate):
        assert 0.0 <= v <= 1.0
    assert rep.hit_rate_at_1 <= rep.hit_rate_at_3
    assert rep.positive_in_candidate_rate == pytest.approx(1.0)  # chosen always in candidates


def test_mlp_scorer_smoke(trips: pd.DataFrame, master) -> None:
    cfg = RecsysConfig()
    samples = build_dataset(trips, cfg)
    scorer = MlpPairScorer(cfg).fit(samples, master)
    s = samples[0]
    cands = generate_candidates(s, master, cfg)
    ranked = scorer.rank(s, cands, master)
    assert set(ranked) == {c.station_id for c in cands}  # permutation, even in fallback

"""Recommendation serving for the API (V1_Prompt §15).

Lazily builds a small ShockFlowRecFormerRetriever + Reranker over the bundled Citi Bike sample
fixture (deterministic, offline) and serves RENT/RETURN Top-3 with reason codes. torch/recsys are
imported lazily so the v0 API still starts without the ``[recsys]`` extra; if they are absent, the
endpoint returns an explicit degraded error instead of a fabricated result (invariant 6, §12).

This is a labelled **policy_simulation / simulated** demo model trained on the sample fixture — not
the measured recommendation model — and says so in every response.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_TRIPS = _ROOT / "data" / "fixtures" / "citibike_sample.csv"
_GBFS = _ROOT / "data" / "fixtures" / "gbfs_station_status.json"
# Fixed demo cutoff (the sample trips are on 2026-07-12); requests may override.
_DEMO_CUTOFF = datetime.fromisoformat("2026-07-12T14:00:00-04:00")

DEMO_NOTE = (
    "정책 시뮬레이션 데모: 샘플 fixture로 학습된 소형 retriever+reranker이며, 측정된 추천 모델이 "
    "아닙니다. 결과는 simulated이고 실제 사용자 지표가 아닙니다."
)


class RecsysUnavailable(RuntimeError):
    """Raised when torch / the recsys extra is not installed."""


@lru_cache(maxsize=1)
def _engine():
    try:
        import pandas as pd
        import torch  # noqa: F401

        from config.recsys import RetrieverConfig
        from ml.recsys import build_dataset, build_station_master
        from ml.recsys.policy import PolicyConfig as PCfg
        from ml.recsys.reranker import ShockFlowRecFormerReranker
        from ml.recsys.retriever import build_index, train_retriever
        from ml.recsys.serving import RecommendationEngine
        from ml.recsys.tokenize import RetrieverTokenizer
    except ImportError as e:
        raise RecsysUnavailable(
            "recommendation model needs the [recsys] extra (pip install -e .[recsys])"
        ) from e

    trips = pd.read_csv(_TRIPS)
    master = build_station_master(trips, gbfs_status_path=_GBFS)
    cfg = RetrieverConfig(
        d_model=32, embedding_dim=32, nhead=4, num_layers=1, dim_feedforward=64,
        dropout=0.0, epochs=1, batch_size=8, max_train_samples=12, seed=0,
    )
    tok = RetrieverTokenizer(master, cfg)
    samples = build_dataset(trips)
    model, tok = train_retriever(samples, master, cfg, tokenizer=tok)
    reranker = ShockFlowRecFormerReranker(cfg)
    index = build_index(model, master, tok, cutoff=_DEMO_CUTOFF.isoformat())
    return RecommendationEngine(model, reranker, index, master, tok, cfg, PCfg(top_k=3))


def recommend(mode: str, lat: float, lng: float, cutoff: datetime | None, is_member: bool = True):
    from contracts.v1.enums import RecommendationMode
    from ml.recsys.serving import query_from_request

    engine = _engine()
    rec_mode = RecommendationMode(mode)
    q = query_from_request(rec_mode, lat, lng, cutoff or _DEMO_CUTOFF, is_member=is_member)
    result, failures = engine.recommend(q, request_id="api")
    return result, failures


def compare_event_impact(mode: str, lat: float, lng: float, cutoff: datetime | None):
    from contracts.v1.enums import RecommendationMode
    from ml.recsys.serving import query_from_request

    engine = _engine()
    q = query_from_request(RecommendationMode(mode), lat, lng, cutoff or _DEMO_CUTOFF)
    return engine.compare_event_impact(q, "api", events=None)  # no event overlap in demo

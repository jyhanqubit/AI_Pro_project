"""B3 — non-attention MLP pair scorer (V1_Prompt §13, sklearn; no PyTorch needed).

Scores each (query, candidate) pair with an ``MLPClassifier`` trained to predict whether the
candidate was the historically chosen station. Pair features are query features + geometry +
(masked) inventory. The chosen station id is never a feature (leakage guard). The scaler is fit on
train only.
"""

from __future__ import annotations

import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

from config.recsys import RecsysConfig
from contracts.v1.enums import RecommendationMode

from .candidates import Candidate, generate_candidates
from .dataset import RecSample
from .stations import StationMaster

_FEATURES = [
    "distance_km",
    "detour_km",
    "hour",
    "dow",
    "is_member",
    "is_return",
    "inventory_known",
    "headroom",
    "capacity",
]


def _pair_row(sample: RecSample, cand: Candidate, master: StationMaster) -> list[float]:
    st = master.get(cand.station_id)
    known = 1.0 if cand.inventory_known else 0.0
    if st is not None and st.inventory_known:
        headroom = float(
            (st.bikes_available or 0)
            if sample.mode == RecommendationMode.RENT
            else (st.docks_available or 0)
        )
        capacity = float(st.capacity or 0)
    else:
        headroom = 0.0
        capacity = 0.0
    return [
        cand.distance_km,
        cand.detour_km,
        float(sample.hour),
        float(sample.dow),
        float(sample.is_member),
        float(sample.mode == RecommendationMode.RETURN),
        known,
        headroom,
        capacity,
    ]


class MlpPairScorer:
    def __init__(self, config: RecsysConfig | None = None) -> None:
        self.cfg = config or RecsysConfig()
        self._scaler = StandardScaler()
        self._clf = MLPClassifier(
            hidden_layer_sizes=(32, 16),
            random_state=self.cfg.seed,
            max_iter=300,
        )
        self._fitted = False

    def fit(self, train: list[RecSample], master: StationMaster) -> MlpPairScorer:
        X: list[list[float]] = []
        y: list[int] = []
        for s in train:
            for c in generate_candidates(s, master, self.cfg):
                X.append(_pair_row(s, c, master))
                y.append(1 if c.is_positive else 0)
        Xa = np.asarray(X, dtype=float)
        ya = np.asarray(y, dtype=int)
        # Guard against a degenerate single-class training slice.
        if len(set(ya.tolist())) < 2:
            self._fitted = False
            return self
        self._clf.fit(self._scaler.fit_transform(Xa), ya)
        self._fitted = True
        return self

    def rank(self, sample: RecSample, cands: list[Candidate], master: StationMaster) -> list[str]:
        if not self._fitted or not cands:
            # Deterministic fallback: nearest feasible first.
            return [
                c.station_id
                for c in sorted(cands, key=lambda c: (not c.feasible, c.distance_km))
            ]
        X = self._scaler.transform([_pair_row(sample, c, master) for c in cands])
        proba = self._clf.predict_proba(X)[:, 1]
        order = sorted(
            zip(cands, proba, strict=True),
            key=lambda t: (not t[0].feasible, -float(t[1]), t[0].distance_km),
        )
        return [c.station_id for c, _ in order]

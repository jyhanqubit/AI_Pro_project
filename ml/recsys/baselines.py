"""Recommendation baselines B0–B3 (V1_Prompt §13).

A ranker maps ``(sample, candidates, master) -> ranked station ids``. Feasible candidates always
outrank infeasible ones (hard constraint), then the baseline's score breaks ties.

- B0 nearest feasible          : distance only.
- B1 distance + capacity        : distance minus a headroom bonus (bikes RENT / docks RETURN).
- B2 distance + risk + benefit  : B1 plus a transparent inventory-risk proxy. The proxy is labelled
                                  a heuristic, NOT the measured Phase 06 forecast (invariant 6).
- B3 MLP pair scorer            : sklearn MLPClassifier over pair features (non-attention, §13).
"""

from __future__ import annotations

from collections.abc import Callable

from contracts.v1.enums import RecommendationMode

from .candidates import Candidate
from .dataset import RecSample
from .stations import StationMaster

Ranker = Callable[[RecSample, list[Candidate], StationMaster], list[str]]


def _headroom(master: StationMaster, sid: str, mode: RecommendationMode) -> float:
    st = master.get(sid)
    if st is None or not st.inventory_known:
        return 0.0
    return float(st.bikes_available or 0) if mode == RecommendationMode.RENT else float(
        st.docks_available or 0
    )


def _order(cands: list[Candidate], score: Callable[[Candidate], float]) -> list[str]:
    """Feasible-first, then by descending score, then nearest as a stable tiebreak."""
    return [
        c.station_id
        for c in sorted(cands, key=lambda c: (not c.feasible, -score(c), c.distance_km))
    ]


def b0_nearest_feasible(
    sample: RecSample, cands: list[Candidate], master: StationMaster
) -> list[str]:
    return _order(cands, lambda c: -c.distance_km)


def b1_distance_capacity(
    sample: RecSample, cands: list[Candidate], master: StationMaster
) -> list[str]:
    def score(c: Candidate) -> float:
        return -c.distance_km + 0.05 * _headroom(master, c.station_id, sample.mode)

    return _order(cands, score)


def b2_distance_risk_benefit(
    sample: RecSample, cands: list[Candidate], master: StationMaster,
    risk_fn: Callable[[str], float] | None = None,
) -> list[str]:
    """B1 + an inventory-risk proxy (or an injected forecast-risk fn). Heuristic, not a model."""

    def proxy_risk(sid: str) -> float:
        # Higher risk = the resource the rider needs is scarce -> penalise.
        st = master.get(sid)
        if st is None or not st.inventory_known or st.capacity in (None, 0):
            return 0.0
        have = (st.bikes_available or 0) if sample.mode == RecommendationMode.RENT else (
            st.docks_available or 0
        )
        return 1.0 - min(1.0, have / float(st.capacity or 1))

    risk = risk_fn or proxy_risk

    def score(c: Candidate) -> float:
        return (
            -c.distance_km
            + 0.05 * _headroom(master, c.station_id, sample.mode)
            - 0.5 * risk(c.station_id)
            - 0.2 * c.detour_km
        )

    return _order(cands, score)

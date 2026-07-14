"""Recommendation ranking metrics (V1_Prompt §13).

All metrics are computed only from executed rankings over a held-out chronological split — never
fabricated (invariant 6). Relevance is binary: the single historically-chosen station is the
positive.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .candidates import Candidate


def hit_rate_at_k(ranked_ids: list[str], positive_id: str, k: int) -> float:
    return 1.0 if positive_id in ranked_ids[:k] else 0.0


def reciprocal_rank(ranked_ids: list[str], positive_id: str) -> float:
    for i, sid in enumerate(ranked_ids, start=1):
        if sid == positive_id:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked_ids: list[str], positive_id: str, k: int) -> float:
    for i, sid in enumerate(ranked_ids[:k], start=1):
        if sid == positive_id:
            return 1.0 / math.log2(i + 1)  # ideal DCG = 1 (single relevant at rank 1)
    return 0.0


@dataclass(frozen=True)
class RankingReport:
    n: int
    positive_in_candidate_rate: float
    candidate_coverage: float  # mean candidates per query
    inventory_missing_rate: float
    hit_rate_at_1: float
    hit_rate_at_3: float
    mrr: float
    ndcg_at_3: float

    def as_dict(self) -> dict[str, float]:
        return {
            "n": float(self.n),
            "positive_in_candidate_rate": self.positive_in_candidate_rate,
            "candidate_coverage": self.candidate_coverage,
            "inventory_missing_rate": self.inventory_missing_rate,
            "hit_rate_at_1": self.hit_rate_at_1,
            "hit_rate_at_3": self.hit_rate_at_3,
            "mrr": self.mrr,
            "ndcg_at_3": self.ndcg_at_3,
        }


def evaluate(
    cases: list[tuple[list[Candidate], list[str], str]],
) -> RankingReport:
    """Aggregate ranking metrics.

    ``cases`` is a list of ``(candidates, ranked_station_ids, positive_id)`` per query.
    """
    if not cases:
        return RankingReport(0, 0, 0, 0, 0, 0, 0, 0)

    n = len(cases)
    pic = cov = inv_missing = h1 = h3 = mrr = ndcg = 0.0
    total_cands = 0
    total_missing = 0
    for cands, ranked, pos in cases:
        total_cands += len(cands)
        total_missing += sum(1 for c in cands if not c.inventory_known)
        pic += 1.0 if any(c.is_positive for c in cands) else 0.0
        h1 += hit_rate_at_k(ranked, pos, 1)
        h3 += hit_rate_at_k(ranked, pos, 3)
        mrr += reciprocal_rank(ranked, pos)
        ndcg += ndcg_at_k(ranked, pos, 3)
    cov = total_cands / n
    inv_missing = total_missing / total_cands if total_cands else 0.0
    return RankingReport(
        n=n,
        positive_in_candidate_rate=pic / n,
        candidate_coverage=cov,
        inventory_missing_rate=inv_missing,
        hit_rate_at_1=h1 / n,
        hit_rate_at_3=h3 / n,
        mrr=mrr / n,
        ndcg_at_3=ndcg / n,
    )

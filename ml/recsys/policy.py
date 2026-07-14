"""Feasibility + business policy layer (V1_Prompt §15).

Turns rerank scores into the final ranking. Hard-infeasible candidates are **removed** (never kept
with a penalty); if none remain, ``no_feasible_candidate`` is returned. The final policy score keeps
every component separate for audit, and explanations are **reason codes**, not attention weights.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from contracts.v1.enums import ClaimState, OperatingModeV1, ReasonCode, RecommendationMode
from contracts.v1.recommendation import RecommendationResult, ScoredStation


@dataclass(frozen=True)
class PolicyConfig:
    success_weight: float = 1.0
    operations_weight: float = 0.5
    detour_weight: float = 0.5
    incentive_cost_weight: float = 1.0
    top_k: int = 3
    high_success: float = 0.5
    low_detour_km: float = 0.2
    network_benefit: float = 0.5
    version: str = "policy-v1"


@dataclass
class RerankedCandidate:
    """A feasible candidate carrying separated scores/components (serving fills these)."""

    station_id: str
    mode: RecommendationMode
    distance_km: float
    detour_km: float
    retrieval_score: float
    rerank_score: float
    success_component: float  # rerank softmax prob
    operational_component: float  # network-balance benefit [0,1]
    inventory_fresh: bool
    incentive_component: float = 0.0  # V1-07D pricing fills this; 0 here
    event_impact_component: float = 0.0  # < 0 => event avoided; 0 when no event overlap
    reason_codes: list[ReasonCode] = field(default_factory=list)


def _final_score(c: RerankedCandidate, cfg: PolicyConfig) -> float:
    return (
        c.rerank_score
        + cfg.success_weight * c.success_component
        + cfg.operations_weight * c.operational_component
        - cfg.detour_weight * c.detour_km
        - cfg.incentive_cost_weight * c.incentive_component
    )


def _reason_codes(c: RerankedCandidate, cfg: PolicyConfig) -> list[ReasonCode]:
    codes: list[ReasonCode] = []
    if c.success_component >= cfg.high_success:
        codes.append(ReasonCode.HIGH_SUCCESS_PROBABILITY)
    if c.detour_km <= cfg.low_detour_km:
        codes.append(ReasonCode.LOW_DETOUR)
    if c.inventory_fresh and c.operational_component >= cfg.network_benefit:
        codes.append(
            ReasonCode.LOW_SHORTAGE_RISK
            if c.mode == RecommendationMode.RENT
            else ReasonCode.LOW_OVERFLOW_RISK
        )
        codes.append(ReasonCode.NETWORK_BALANCE_BENEFIT)
    if c.event_impact_component < 0:
        codes.append(ReasonCode.EVENT_IMPACT_AVOIDED)
    if not c.inventory_fresh:
        codes.append(ReasonCode.INVENTORY_STALE)
    return codes


def apply_policy(
    request_id: str,
    mode: RecommendationMode,
    cutoff: datetime,
    feasible: list[RerankedCandidate],
    retriever_version: str,
    reranker_version: str,
    cfg: PolicyConfig | None = None,
    operating_mode: OperatingModeV1 = OperatingModeV1.POLICY_SIMULATION,
    claim_state: ClaimState = ClaimState.SIMULATED,
) -> RecommendationResult:
    """Rank the already-feasible candidates and build the typed result (§15)."""
    cfg = cfg or PolicyConfig()
    if not feasible:
        return RecommendationResult(
            request_id=request_id, mode=mode, cutoff=cutoff,
            retriever_version=retriever_version, reranker_version=reranker_version,
            stations=[], no_feasible_candidate=True,
            claim_state=claim_state, operating_mode=operating_mode,
        )

    scored = sorted(feasible, key=lambda c: -_final_score(c, cfg))[: cfg.top_k]
    stations = [
        ScoredStation(
            station_id=c.station_id,
            rank=i + 1,
            distance_km=round(c.distance_km, 4),
            detour_km=round(c.detour_km, 4),
            feasible=True,
            retrieval_score=round(c.retrieval_score, 4),
            rerank_score=round(c.rerank_score, 4),
            success_component=round(c.success_component, 4),
            operational_component=round(c.operational_component, 4),
            detour_component=round(c.detour_km, 4),
            incentive_component=round(c.incentive_component, 4),
            final_policy_score=round(_final_score(c, cfg), 4),
            reason_codes=_reason_codes(c, cfg),
            inventory_is_stale=not c.inventory_fresh,
        )
        for i, c in enumerate(scored)
    ]
    return RecommendationResult(
        request_id=request_id, mode=mode, cutoff=cutoff,
        retriever_version=retriever_version, reranker_version=reranker_version,
        stations=stations, no_feasible_candidate=False,
        claim_state=claim_state, operating_mode=operating_mode,
    )

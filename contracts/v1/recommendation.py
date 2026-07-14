"""Station recommendation + incentive contracts (V1_Prompt §13–§16).

Context-aware station ranking (RENT/RETURN), not personalised collaborative filtering. Every
scored candidate keeps its component scores separate so the policy score is auditable; hard
infeasible candidates are removed (never surfaced with a penalty). Explanations are reason codes,
not attention weights.
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field, model_validator

from contracts.common import ContractModel

from .enums import ClaimState, OperatingModeV1, ReasonCode, RecommendationMode


class RecommendationRequest(ContractModel):
    request_id: str = Field(min_length=1)
    mode: RecommendationMode
    origin_lat: float = Field(ge=-90.0, le=90.0)
    origin_lng: float = Field(ge=-180.0, le=180.0)
    cutoff: AwareDatetime
    max_detour_km: float = Field(default=1.0, ge=0.0)
    radius_km: float = Field(default=1.5, gt=0.0)
    top_k: int = Field(default=3, gt=0)
    query_is_synthetic: bool = Field(
        default=False,
        description="True when derived from a historical choice via geographic jitter (§13).",
    )
    operating_mode: OperatingModeV1


class IncentiveQuote(ContractModel):
    """Pickup/return credit (never a base-fare surcharge) for a station (V1_Prompt §16)."""

    station_id: str = Field(min_length=1)
    credit: float = Field(ge=0.0, description="Credit tier value; 0 means no incentive.")
    budget_ok: bool = True
    is_simulated: bool = Field(default=True)
    disclaimer: str = Field(default="SIMULATED OUTCOME — NOT A LIVE BUSINESS RESULT")


class ScoredStation(ContractModel):
    """One ranked candidate with its component scores kept separate (V1_Prompt §15)."""

    station_id: str = Field(min_length=1)
    rank: int = Field(ge=1)
    distance_km: float = Field(ge=0.0)
    detour_km: float = Field(ge=0.0)
    feasible: bool

    retrieval_score: float | None = None
    rerank_score: float | None = None
    success_component: float | None = None
    operational_component: float | None = None
    detour_component: float | None = None
    incentive_component: float | None = None
    final_policy_score: float

    reason_codes: list[ReasonCode] = Field(default_factory=list)
    incentive: IncentiveQuote | None = None
    inventory_is_stale: bool = False


class RecommendationResult(ContractModel):
    request_id: str = Field(min_length=1)
    mode: RecommendationMode
    cutoff: AwareDatetime
    retriever_version: str = Field(min_length=1)
    reranker_version: str = Field(min_length=1)
    stations: list[ScoredStation] = Field(default_factory=list)
    no_feasible_candidate: bool = False
    claim_state: ClaimState
    operating_mode: OperatingModeV1

    @model_validator(mode="after")
    def _feasibility(self) -> RecommendationResult:
        if self.no_feasible_candidate and self.stations:
            raise ValueError("no_feasible_candidate=True must return an empty station list")
        # Surfaced candidates must be feasible (hard constraints remove, not penalise).
        if any(not s.feasible for s in self.stations):
            raise ValueError("infeasible candidates must be removed before ranking")
        return self

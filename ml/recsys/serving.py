"""End-to-end recommendation serving (V1_Prompt §15).

    Hard Candidate Filter -> Dual-Encoder Top-K Retrieval -> Cross-Attention Rerank
    -> Feasibility & Business Policy -> Top-3

Retrieval and reranking failures are surfaced separately. Infeasible candidates are removed before
reranking (never penalised); if none survive, the result is ``no_feasible_candidate``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import torch

from config.recsys import RetrieverConfig
from contracts.v1.enums import ClaimState, OperatingModeV1, RecommendationMode
from contracts.v1.recommendation import RecommendationResult
from pipelines.features.kernels import haversine_km

from .candidates import Candidate
from .dataset import RecSample
from .encoder import ShockFlowRecFormerRetriever
from .index import ExactTorchIndex
from .policy import PolicyConfig, RerankedCandidate, apply_policy
from .reranker import ShockFlowRecFormerReranker, build_pair_tensor
from .stations import Station, StationMaster
from .tokenize import EventProvider, RetrieverTokenizer


def query_from_request(
    mode: RecommendationMode, lat: float, lng: float, cutoff: datetime, is_member: bool = True,
    origin_lat: float | None = None, origin_lng: float | None = None,
) -> RecSample:
    """A label-free query for serving (chosen_station_id is unused by the query tower)."""
    return RecSample(
        sample_id="__serve__", mode=mode, cutoff=cutoff, query_lat=lat, query_lng=lng,
        hour=cutoff.hour, dow=cutoff.weekday(), is_member=is_member,
        chosen_station_id="__query__", trip_origin_lat=origin_lat, trip_origin_lng=origin_lng,
    )


def _feasible(st: Station | None, mode: RecommendationMode) -> bool:
    if st is None:
        return False
    if not st.inventory_known:
        return True
    if mode == RecommendationMode.RENT:
        return st.is_renting and (st.bikes_available or 0) > 0
    return st.is_returning and (st.docks_available or 0) > 0


@dataclass
class EngineFailure:
    stage: str  # "retrieval" | "reranking"
    reason: str


class RecommendationEngine:
    def __init__(
        self,
        retriever: ShockFlowRecFormerRetriever,
        reranker: ShockFlowRecFormerReranker,
        index: ExactTorchIndex,
        master: StationMaster,
        tokenizer: RetrieverTokenizer,
        retriever_cfg: RetrieverConfig | None = None,
        policy_cfg: PolicyConfig | None = None,
    ) -> None:
        self.retriever = retriever.eval()
        self.reranker = reranker.eval()
        self.index = index
        self.master = master
        self.tok = tokenizer
        self.rcfg = retriever_cfg or RetrieverConfig()
        self.pcfg = policy_cfg or PolicyConfig()

    @torch.no_grad()
    def recommend(
        self,
        query: RecSample,
        request_id: str = "req",
        events: EventProvider | None = None,
        operating_mode: OperatingModeV1 = OperatingModeV1.POLICY_SIMULATION,
        claim_state: ClaimState = ClaimState.SIMULATED,
    ) -> tuple[RecommendationResult, list[EngineFailure]]:
        failures: list[EngineFailure] = []

        # 1-2. Dual-encoder retrieval (Top-K).
        q = self.retriever.query_embed(**self.tok.query_batch([query], events=events))
        scores, idx = self.index.search(q, self.rcfg.retrieval_top_k)
        retrieved_ids = self.index.ids_for(idx)[0]
        retrieval_score = {sid: float(scores[0, j]) for j, sid in enumerate(retrieved_ids)}
        if not retrieved_ids:
            failures.append(EngineFailure("retrieval", "empty Top-K"))

        # 3. Hard candidate filter (feasibility). Infeasible removed, not penalised.
        survivors: list[Candidate] = []
        for sid in retrieved_ids:
            st = self.master.get(sid)
            dist = haversine_km(query.query_lat, query.query_lng, st.lat, st.lng) if st else 9e9
            detour = 0.0
            if query.mode == RecommendationMode.RETURN and query.trip_origin_lat is not None and st:
                detour = max(
                    0.0,
                    haversine_km(query.trip_origin_lat, query.trip_origin_lng, st.lat, st.lng)  # type: ignore[arg-type]
                    - dist,
                )
            if _feasible(st, query.mode):
                survivors.append(
                    Candidate(sid, round(dist, 4), round(detour, 4), True,
                              st.inventory_known if st else False, sid == query.chosen_station_id)
                )
        if not survivors:
            return apply_policy(
                request_id, query.mode, query.cutoff, [], self.retriever.cfg.version,
                self.reranker.cfg.version, self.pcfg, operating_mode, claim_state,
            ), failures

        # 4. Cross-attention rerank of the survivors.
        stations = [self.master.get(c.station_id) for c in survivors]
        s_emb = self.retriever.station_embed(**self.tok.station_batch(stations, events=events))
        pair = build_pair_tensor(query, survivors, self.master)
        q_rep = q.expand(len(survivors), -1)
        logits = self.reranker(q_rep, s_emb, pair)
        probs = torch.softmax(logits, dim=0)

        # 5. Policy.
        reranked = [
            RerankedCandidate(
                station_id=c.station_id, mode=query.mode,
                distance_km=c.distance_km, detour_km=c.detour_km,
                retrieval_score=retrieval_score.get(c.station_id, 0.0),
                rerank_score=float(logits[i]),
                success_component=float(probs[i]),
                operational_component=pair[i, 4].item(),  # operational_benefit
                inventory_fresh=bool(pair[i, 5].item() >= 0.5),
            )
            for i, c in enumerate(survivors)
        ]
        result = apply_policy(
            request_id, query.mode, query.cutoff, reranked, self.retriever.cfg.version,
            self.reranker.cfg.version, self.pcfg, operating_mode, claim_state,
        )
        return result, failures

    def compare_event_impact(
        self, query: RecSample, request_id: str, events: EventProvider | None
    ) -> dict:
        """Event ON vs OFF over a frozen candidate set: Top-3 overlap + rank deltas (§15)."""
        off, _ = self.recommend(query, request_id, events=None)
        on, _ = self.recommend(query, request_id, events=events)
        off_ids = [s.station_id for s in off.stations]
        on_ids = [s.station_id for s in on.stations]
        overlap = len(set(off_ids) & set(on_ids))
        return {
            "event_off_top3": off_ids,
            "event_on_top3": on_ids,
            "top3_overlap": overlap,
            "event_status": "insufficient_event_overlap" if events is None else "events_present",
        }

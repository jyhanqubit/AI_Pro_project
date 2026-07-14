"""ShockFlowRecFormerReranker — cross-attention reranker (V1_Prompt §15).

One Transformer processes a joint per-pair sequence so query and station tokens cross-attend:

    [CLS, QUERY, SEP, STATION,
     PAIR_DISTANCE, PAIR_DETOUR, PAIR_FORECAST_RISK, PAIR_EVENT_IMPACT,
     PAIR_OPERATIONAL_BENEFIT, PAIR_INVENTORY_FRESHNESS]

QUERY/STATION segment tokens are the dual-encoder tower embeddings; the six PAIR tokens are scalar
pair features projected to d_model. Segment + pair-type embeddings distinguish them. The CLS output
maps to a scalar rerank logit. Training uses listwise softmax cross-entropy (pairwise optional),
with the positive forced into the candidate slate **only in training** (§15).
"""

from __future__ import annotations

import torch
from torch import Tensor, nn

from config.recsys import RetrieverConfig

from .candidates import Candidate
from .dataset import RecSample
from .stations import Station, StationMaster

# Pair feature order == PAIR_* token order.
PAIR_FEATURES = [
    "distance", "detour", "forecast_risk", "event_impact",
    "operational_benefit", "inventory_freshness",
]
N_PAIR = len(PAIR_FEATURES)
# Segment ids for CLS, QUERY, SEP, STATION, PAIR.
_SEG_CLS, _SEG_QUERY, _SEG_SEP, _SEG_STATION, _SEG_PAIR = range(5)


def pair_features(
    sample: RecSample,
    cand: Candidate,
    station: Station | None,
    forecast_risk: float = 0.0,
    event_impact: float = 0.0,
) -> list[float]:
    """The six PAIR-token scalar features. Absent signals are 0 with the freshness flag = 0."""
    if station is not None and station.inventory_known and station.capacity:
        from contracts.v1.enums import RecommendationMode

        have = (station.bikes_available or 0) if sample.mode == RecommendationMode.RENT else (
            station.docks_available or 0
        )
        operational_benefit = min(1.0, have / float(station.capacity))
        freshness = 1.0
    else:
        operational_benefit = 0.0
        freshness = 0.0
    return [
        cand.distance_km, cand.detour_km, forecast_risk, event_impact,
        operational_benefit, freshness,
    ]


class ShockFlowRecFormerReranker(nn.Module):
    def __init__(self, cfg: RetrieverConfig) -> None:
        super().__init__()
        d = cfg.d_model
        self.cfg = cfg
        self.q_proj = nn.Linear(cfg.embedding_dim, d)
        self.s_proj = nn.Linear(cfg.embedding_dim, d)
        self.pair_proj = nn.Linear(1, d)
        self.seg_emb = nn.Embedding(5, d)
        self.pair_type = nn.Embedding(N_PAIR, d)
        self.cls = nn.Parameter(torch.zeros(1, d))
        self.sep = nn.Parameter(torch.zeros(1, d))
        nn.init.normal_(self.cls, std=0.02)
        nn.init.normal_(self.sep, std=0.02)
        layer = nn.TransformerEncoderLayer(
            d_model=d, nhead=cfg.nhead, dim_feedforward=cfg.dim_feedforward,
            dropout=cfg.dropout, batch_first=True, activation="gelu",
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=cfg.num_layers)
        self.head = nn.Linear(d, 1)

    def forward(self, q: Tensor, s: Tensor, pair_feats: Tensor) -> Tensor:
        """(P,D),(P,D),(P,6) -> (P,) rerank logits."""
        p = q.shape[0]
        dev = q.device
        seg = lambda i, n: self.seg_emb(torch.full((p, n), i, dtype=torch.long, device=dev))  # noqa: E731

        cls = self.cls.expand(p, 1, -1) + seg(_SEG_CLS, 1)
        q_seg = self.seg_emb(torch.full((p,), _SEG_QUERY, device=dev))
        query = (self.q_proj(q) + q_seg).unsqueeze(1)
        sep = self.sep.expand(p, 1, -1) + seg(_SEG_SEP, 1)
        station = (
            self.s_proj(s) + self.seg_emb(torch.full((p,), _SEG_STATION, device=dev))
        ).unsqueeze(1)
        # Pair tokens: project each scalar, add segment + pair-type embedding.
        pf = self.pair_proj(pair_feats.unsqueeze(-1))  # (P, 6, d)
        pf = pf + self.seg_emb(torch.full((p, N_PAIR), _SEG_PAIR, dtype=torch.long, device=dev))
        pf = pf + self.pair_type(torch.arange(N_PAIR, device=dev)).unsqueeze(0)

        seq = torch.cat([cls, query, sep, station, pf], dim=1)  # (P, 10, d)
        encoded = self.encoder(seq)
        return self.head(encoded[:, 0]).squeeze(-1)  # (P,)


def listwise_loss(logits: Tensor, positive_idx: int) -> Tensor:
    """Softmax cross-entropy over one query's candidate logits (default loss, §15)."""
    target = torch.tensor([positive_idx], device=logits.device)
    return nn.functional.cross_entropy(logits.unsqueeze(0), target)


def pairwise_loss(logits: Tensor, positive_idx: int, margin: float = 1.0) -> Tensor:
    """Optional pairwise hinge: positive should outscore each negative by a margin (§15)."""
    pos = logits[positive_idx]
    neg = torch.cat([logits[:positive_idx], logits[positive_idx + 1 :]])
    if neg.numel() == 0:
        return logits.new_zeros(())
    return torch.clamp(margin - (pos - neg), min=0.0).mean()


def build_pair_tensor(
    sample: RecSample,
    cands: list[Candidate],
    master: StationMaster,
    forecast_risk: float = 0.0,
) -> Tensor:
    """(K, 6) pair-feature tensor for a query's candidate list."""
    rows = [pair_features(sample, c, master.get(c.station_id), forecast_risk) for c in cands]
    return torch.tensor(rows, dtype=torch.float)

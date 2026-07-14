"""ShockFlowRecFormerRetriever — attention dual-encoder for station retrieval (V1_Prompt §14).

Two Transformer towers (query / station) over multi-token sequences. Each token group has its own
feature projector; absent optional feature groups are replaced by a learned
``MissingValueMaskEmbedding`` (missing is informative), and variable-length EVENT tokens use a real
attention **padding mask**. The CLS token's L2-normalised output is the tower embedding; the
retrieval score is a temperature-scaled dot product, trained with InfoNCE.

No external pretrained weights are downloaded (required-path rule). Deterministic given seed +
inputs.
"""

from __future__ import annotations

import torch
from torch import Tensor, nn

from config.recsys import RetrieverConfig

# Token layouts (CLS is prepended by the tower). EVENT tokens are appended, padding-masked.
QUERY_SCALAR_TOKENS = ["MODE", "GEO", "TIME", "CONSTRAINT", "FORECAST", "LOCAL_INVENTORY"]
STATION_SCALAR_TOKENS = ["STATION_STATIC", "STATION_GEO", "INVENTORY", "FORECAST", "OPERATION"]
# Optional groups whose absence triggers the MissingValueMaskEmbedding (vs. always-present groups).
OPTIONAL_TOKENS = {"FORECAST", "LOCAL_INVENTORY", "INVENTORY"}

EVENT_FEAT_DIM = 4  # severity, confidence, signed direction, recency_norm
RECENCY_BUCKETS = 5


# --- Feature projectors (each named per V1_Prompt §14) ------------------------------------------
class _NumericMLP(nn.Module):
    """Shared numeric->d_model projection (Linear + LayerNorm + GELU)."""

    def __init__(self, in_dim: int, d_model: int) -> None:
        super().__init__()
        self.net = nn.Sequential(nn.Linear(in_dim, d_model), nn.LayerNorm(d_model), nn.GELU())

    def forward(self, x: Tensor) -> Tensor:
        return self.net(x)


class NumericFeatureProjector(_NumericMLP):
    pass


class GeoFeatureProjector(_NumericMLP):
    """Projects (lat, lng) — optionally lightly Fourier-expanded — into d_model."""


class ForecastFeatureProjector(_NumericMLP):
    pass


class InventoryFeatureProjector(_NumericMLP):
    pass


class EventFeatureProjector(_NumericMLP):
    pass


class CategoricalEmbeddingProjector(nn.Module):
    def __init__(self, num_categories: int, d_model: int) -> None:
        super().__init__()
        self.emb = nn.Embedding(num_categories, d_model)

    def forward(self, idx: Tensor) -> Tensor:
        return self.emb(idx)


class MissingValueMaskEmbedding(nn.Module):
    """A learned vector per optional token, substituted when that feature group is absent."""

    def __init__(self, token_names: list[str], d_model: int) -> None:
        super().__init__()
        self._index = {n: i for i, n in enumerate(token_names)}
        self.emb = nn.Embedding(max(1, len(token_names)), d_model)

    def forward(self, token: str, batch: int, device: torch.device) -> Tensor:
        i = self._index[token]
        idx = torch.full((batch,), i, dtype=torch.long, device=device)
        return self.emb(idx)


# --- Feature spec per tower ---------------------------------------------------------------------
def _query_feat_dims() -> dict[str, int]:
    return {"GEO": 2, "TIME": 4, "CONSTRAINT": 3, "FORECAST": 3, "LOCAL_INVENTORY": 3}


def _station_feat_dims() -> dict[str, int]:
    return {"STATION_GEO": 2, "INVENTORY": 3, "FORECAST": 3, "OPERATION": 3}


class _Tower(nn.Module):
    """One Transformer tower over [CLS, scalar tokens..., EVENT tokens...]."""

    def __init__(
        self,
        cfg: RetrieverConfig,
        scalar_tokens: list[str],
        feat_dims: dict[str, int],
        n_categories: dict[str, int],  # categorical token -> vocab size
    ) -> None:
        super().__init__()
        d = cfg.d_model
        self.cfg = cfg
        self.scalar_tokens = scalar_tokens
        self._optional = [t for t in scalar_tokens if t in OPTIONAL_TOKENS]

        # Projectors per token.
        self.projectors = nn.ModuleDict()
        for t in scalar_tokens:
            if t in n_categories:
                self.projectors[t] = CategoricalEmbeddingProjector(n_categories[t], d)
            elif t in ("GEO", "STATION_GEO"):
                self.projectors[t] = GeoFeatureProjector(feat_dims[t], d)
            elif t == "FORECAST":
                self.projectors[t] = ForecastFeatureProjector(feat_dims[t], d)
            elif t in ("INVENTORY", "LOCAL_INVENTORY"):
                self.projectors[t] = InventoryFeatureProjector(feat_dims[t], d)
            else:
                self.projectors[t] = NumericFeatureProjector(feat_dims[t], d)
        self.event_projector = EventFeatureProjector(EVENT_FEAT_DIM, d)

        # Token-type, recency, missing, and CLS embeddings.
        self.type_emb = nn.Embedding(len(scalar_tokens) + 2, d)  # +CLS +EVENT type
        self.recency_emb = nn.Embedding(RECENCY_BUCKETS, d)
        self.missing = MissingValueMaskEmbedding(self._optional, d)
        self.cls = nn.Parameter(torch.zeros(1, 1, d))
        nn.init.normal_(self.cls, std=0.02)

        layer = nn.TransformerEncoderLayer(
            d_model=d, nhead=cfg.nhead, dim_feedforward=cfg.dim_feedforward,
            dropout=cfg.dropout, batch_first=True, activation="gelu",
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=cfg.num_layers)
        self.out = nn.Linear(d, cfg.embedding_dim)
        self._cls_type = len(scalar_tokens)
        self._event_type = len(scalar_tokens) + 1

    def forward(
        self,
        scalar_feats: dict[str, Tensor],
        scalar_present: dict[str, Tensor],
        event_feats: Tensor,  # (B, E, EVENT_FEAT_DIM)
        event_present: Tensor,  # (B, E) bool
        event_recency: Tensor,  # (B, E) long bucket
    ) -> Tensor:
        b = event_feats.shape[0]
        device = event_feats.device
        toks: list[Tensor] = []

        # CLS.
        cls = self.cls.expand(b, 1, -1) + self.type_emb(
            torch.full((b, 1), self._cls_type, dtype=torch.long, device=device)
        )
        toks.append(cls)

        # Scalar tokens (always in the sequence; absent optional groups -> missing embedding).
        for i, t in enumerate(self.scalar_tokens):
            proj = self.projectors[t](scalar_feats[t])
            if t in self._optional:
                present = scalar_present[t].unsqueeze(-1)  # (B,1)
                miss = self.missing(t, b, device)
                proj = torch.where(present, proj, miss)
            proj = proj + self.type_emb(
                torch.full((b,), i, dtype=torch.long, device=device)
            )
            toks.append(proj.unsqueeze(1))

        # Event tokens (padding-masked).
        ev = self.event_projector(event_feats)  # (B,E,d)
        ev = ev + self.recency_emb(event_recency)
        ev = ev + self.type_emb(
            torch.full((b, event_feats.shape[1]), self._event_type, dtype=torch.long, device=device)
        )
        toks.append(ev)

        seq = torch.cat(toks, dim=1)  # (B, T, d)

        n_fixed = 1 + len(self.scalar_tokens)
        # key_padding_mask: True => ignore. CLS + scalar tokens present; events by mask.
        pad = torch.zeros(b, seq.shape[1], dtype=torch.bool, device=device)
        pad[:, n_fixed:] = ~event_present
        encoded = self.encoder(seq, src_key_padding_mask=pad)
        emb = self.out(encoded[:, 0])  # CLS
        return nn.functional.normalize(emb, dim=-1)


class ShockFlowRecFormerRetriever(nn.Module):
    """Dual-encoder retriever. ``query_embed``/``station_embed`` -> L2-normalised vectors; score is
    a temperature-scaled dot product; ``info_nce`` trains it (V1_Prompt §14)."""

    def __init__(self, cfg: RetrieverConfig, num_stations: int) -> None:
        super().__init__()
        self.cfg = cfg
        self.query_tower = _Tower(
            cfg, QUERY_SCALAR_TOKENS, _query_feat_dims(), n_categories={"MODE": 2}
        )
        self.station_tower = _Tower(
            cfg,
            STATION_SCALAR_TOKENS,
            _station_feat_dims(),
            n_categories={"STATION_STATIC": num_stations + 1},  # +1 OOV for cold-start
        )

    def query_embed(self, **kw: Tensor) -> Tensor:
        return self.query_tower(**kw)

    def station_embed(self, **kw: Tensor) -> Tensor:
        return self.station_tower(**kw)

    def score(self, q: Tensor, s: Tensor) -> Tensor:
        """Temperature-scaled dot product between query and station embeddings."""
        return (q @ s.T) / self.cfg.temperature

    def info_nce(
        self, q: Tensor, s_pos: Tensor, s_neg: Tensor | None, false_neg_mask: Tensor | None = None
    ) -> Tensor:
        """InfoNCE with in-batch negatives (other rows' positives) + optional explicit hard
        negatives. ``false_neg_mask`` (B,B) True marks in-batch columns that are actually the same
        chosen station as the row's positive — masked out to avoid false negatives (§14)."""
        logits_pos = self.score(q, s_pos)  # (B,B): diagonal = true positive
        b = q.shape[0]
        target = torch.arange(b, device=q.device)
        if false_neg_mask is not None:
            off_diag = false_neg_mask & (~torch.eye(b, dtype=torch.bool, device=q.device))
            logits_pos = logits_pos.masked_fill(off_diag, float("-inf"))
        logits = logits_pos
        if s_neg is not None and s_neg.numel() > 0:
            logits_neg = self.score(q, s_neg)  # (B, N)
            logits = torch.cat([logits_pos, logits_neg], dim=1)
        return nn.functional.cross_entropy(logits, target)

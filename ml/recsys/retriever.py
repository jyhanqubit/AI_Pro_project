"""Train + evaluate the ShockFlowRecFormerRetriever (V1_Prompt §14).

Training: unique-station-column InfoNCE. Each batch's columns are the *deduplicated* set of the
batch's positive stations plus per-row hard negatives (nearest non-chosen candidates). Deduplicating
stations into columns makes duplicate positives share one column, which prevents the false-negative
problem (§14) by construction, while still exposing in-batch + hard negatives.

Evaluation: exact Top-K retrieval → Recall@5/10/20, MRR@20, NDCG@20, split by seen vs cold-start
station, with embedding/search latency. Event tokens are absent on plain Trip History, so the
event ablation records ``insufficient_event_overlap`` instead of a fabricated lift (§14).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import torch
from torch import Tensor

from config.recsys import RetrieverConfig

from .candidates import generate_candidates
from .dataset import RecSample
from .encoder import ShockFlowRecFormerRetriever
from .index import ExactTorchIndex, IndexKey, station_snapshot_hash
from .stations import StationMaster
from .tokenize import EventProvider, ForecastProvider, RetrieverTokenizer


def _seed(cfg: RetrieverConfig) -> None:
    torch.manual_seed(cfg.seed)


def train_retriever(
    train: list[RecSample],
    master: StationMaster,
    cfg: RetrieverConfig | None = None,
    tokenizer: RetrieverTokenizer | None = None,
    forecast: ForecastProvider | None = None,
    events: EventProvider | None = None,
) -> tuple[ShockFlowRecFormerRetriever, RetrieverTokenizer]:
    cfg = cfg or RetrieverConfig()
    _seed(cfg)
    tok = tokenizer or RetrieverTokenizer(master, cfg)
    model = ShockFlowRecFormerRetriever(cfg, num_stations=tok.num_stations)
    opt = torch.optim.Adam(model.parameters(), lr=cfg.lr)

    data = train[: cfg.max_train_samples]
    model.train()
    for _ in range(cfg.epochs):
        for start in range(0, len(data), cfg.batch_size):
            batch = data[start : start + cfg.batch_size]
            loss = _batch_loss(model, tok, master, batch, cfg, forecast, events)
            if loss is None:
                continue
            opt.zero_grad()
            loss.backward()
            opt.step()
    model.eval()
    return model, tok


def _batch_loss(model, tok, master, batch, cfg, forecast, events) -> Tensor | None:
    # Column stations = dedup(positives + hard negatives).
    col_ids: list[str] = []
    seen: set[str] = set()

    def add(sid: str) -> None:
        if sid not in seen and master.get(sid) is not None:
            seen.add(sid)
            col_ids.append(sid)

    for s in batch:
        add(s.chosen_station_id)
        cands = generate_candidates(s, master)  # uses RecsysConfig() default
        negs = [c.station_id for c in cands if not c.is_positive][: cfg.hard_negatives]
        for sid in negs:
            add(sid)
    if len(col_ids) < 2:
        return None

    col_index = {sid: i for i, sid in enumerate(col_ids)}
    target = torch.tensor([col_index[s.chosen_station_id] for s in batch], dtype=torch.long)

    q = model.query_embed(**tok.query_batch(batch, forecast, events))
    col_stations = [master.get(sid) for sid in col_ids]
    s_emb = model.station_embed(**tok.station_batch(col_stations, forecast, events))
    logits = model.score(q, s_emb)  # (B, M)
    return torch.nn.functional.cross_entropy(logits, target)


@dataclass
class RetrievalReport:
    n: int
    recall_at_5: float
    recall_at_10: float
    recall_at_20: float
    mrr_at_20: float
    ndcg_at_20: float
    cold_start_n: int
    cold_start_recall_at_20: float
    embed_ms_per_query: float
    search_ms_per_query: float
    event_status: str

    def as_dict(self) -> dict[str, float | str]:
        return self.__dict__.copy()


@torch.no_grad()
def build_index(
    model: ShockFlowRecFormerRetriever,
    master: StationMaster,
    tok: RetrieverTokenizer,
    cutoff: str,
    feature_version: str = "recsys-v1",
    event_feature_version: str = "none",
    forecast: ForecastProvider | None = None,
    events: EventProvider | None = None,
) -> ExactTorchIndex:
    stations = master.all()
    emb = model.station_embed(**tok.station_batch(stations, forecast, events))
    ids = [st.station_id for st in stations]
    key = IndexKey(
        cutoff=cutoff,
        model_version=model.cfg.version,
        feature_version=feature_version,
        event_feature_version=event_feature_version,
        station_snapshot_hash=station_snapshot_hash(ids, emb),
    )
    return ExactTorchIndex(ids, emb, key)


@torch.no_grad()
def evaluate_retriever(
    model: ShockFlowRecFormerRetriever,
    index: ExactTorchIndex,
    test: list[RecSample],
    master: StationMaster,
    tok: RetrieverTokenizer,
    train_chosen: set[str],
    cfg: RetrieverConfig | None = None,
    forecast: ForecastProvider | None = None,
    events: EventProvider | None = None,
    batch_size: int = 512,
) -> RetrievalReport:
    cfg = cfg or RetrieverConfig()
    n = len(test)
    r5 = r10 = r20 = mrr = ndcg = 0.0
    cold_n = cold_r20 = 0
    embed_ms = search_ms = 0.0

    for start in range(0, n, batch_size):
        batch = test[start : start + batch_size]
        t0 = time.perf_counter()
        q = model.query_embed(**tok.query_batch(batch, forecast, events))
        embed_ms += (time.perf_counter() - t0) * 1000
        t1 = time.perf_counter()
        _, idx = index.search(q, cfg.retrieval_top_k)
        search_ms += (time.perf_counter() - t1) * 1000
        ranked = index.ids_for(idx)
        for s, ids in zip(batch, ranked, strict=True):
            pos = s.chosen_station_id
            r5 += 1.0 if pos in ids[:5] else 0.0
            r10 += 1.0 if pos in ids[:10] else 0.0
            hit20 = pos in ids[:20]
            r20 += 1.0 if hit20 else 0.0
            if pos in ids:
                rank = ids.index(pos) + 1
                mrr += 1.0 / rank
                ndcg += 1.0 / math.log2(rank + 1)
            if pos not in train_chosen:  # cold-start positive
                cold_n += 1
                cold_r20 += 1.0 if hit20 else 0.0

    return RetrievalReport(
        n=n,
        recall_at_5=r5 / n, recall_at_10=r10 / n, recall_at_20=r20 / n,
        mrr_at_20=mrr / n, ndcg_at_20=ndcg / n,
        cold_start_n=cold_n,
        cold_start_recall_at_20=(cold_r20 / cold_n) if cold_n else 0.0,
        embed_ms_per_query=embed_ms / n, search_ms_per_query=search_ms / n,
        event_status="insufficient_event_overlap" if events is None else "events_present",
    )

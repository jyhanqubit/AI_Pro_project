"""Train the reranker + measure the end-to-end recommender (V1_Prompt §15).

Freezes the trained retriever, trains the cross-attention reranker with listwise softmax CE (the
positive is always in the candidate list, so it is forced in during training only), then measures
the full Filter -> Retrieve -> Rerank -> Policy -> Top-3 pipeline on a chronological holdout:
HitRate@1/@3, MRR, NDCG@3, feasible@3, no-feasible rate, average detour, and latency. Bounds are
logged, not silent. Event tokens do not overlap plain trip data -> insufficient_event_overlap.

    python -m ml.recsys.reranker_eval           # real JC-202606 (bounded)
    python -m ml.recsys.reranker_eval --sample  # fixture smoke
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import torch

from config.recsys import RetrieverConfig

from .candidates import generate_candidates
from .dataset import build_dataset, chronological_split
from .reranker import (
    ShockFlowRecFormerReranker,
    build_pair_tensor,
    listwise_loss,
)
from .retriever import build_index, train_retriever
from .serving import RecommendationEngine
from .stations import build_station_master
from .tokenize import RetrieverTokenizer

_ROOT = Path(__file__).resolve().parents[2]
_REAL_ZIP = _ROOT / "data" / "raw" / "citibike" / "JC-202606-citibike-tripdata.csv.zip"
_SAMPLE = _ROOT / "data" / "fixtures" / "citibike_sample.csv"
_GBFS = _ROOT / "data" / "fixtures" / "gbfs_station_status.json"
_OUT = _ROOT / "reports" / "v1" / "recsys" / "e2e_metrics.json"

RERANK_TRAIN_CAP = 4000
E2E_EVAL_CAP = 3000


def _load_real() -> pd.DataFrame:
    with zipfile.ZipFile(_REAL_ZIP) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv") and "MACOSX" not in n)
        with z.open(name) as f:
            return pd.read_csv(f)


def train_reranker(retriever, reranker, train, master, tok, cfg, accum: int = 32):
    """Listwise-CE reranker training with the retriever frozen (§15). Positive is in-list."""
    torch.manual_seed(cfg.seed)
    opt = torch.optim.Adam(reranker.parameters(), lr=cfg.lr)
    data = train[:RERANK_TRAIN_CAP]
    retriever.eval()
    reranker.train()
    for _ in range(cfg.epochs):
        opt.zero_grad()
        n_acc = 0
        for s in data:
            cands = generate_candidates(s, master)
            pos = [j for j, c in enumerate(cands) if c.is_positive]
            if not pos or len(cands) < 2:
                continue
            with torch.no_grad():
                q = retriever.query_embed(**tok.query_batch([s]))
                stations = [master.get(c.station_id) for c in cands]
                s_emb = retriever.station_embed(**tok.station_batch(stations))
            pair = build_pair_tensor(s, cands, master)
            logits = reranker(q.expand(len(cands), -1), s_emb, pair)
            loss = listwise_loss(logits, pos[0]) / accum
            loss.backward()
            n_acc += 1
            if n_acc % accum == 0:
                opt.step()
                opt.zero_grad()
        opt.step()
    reranker.eval()
    return reranker


def run(trips: pd.DataFrame, source: str, cfg: RetrieverConfig) -> dict:
    master = build_station_master(trips, gbfs_status_path=_GBFS)
    samples = build_dataset(trips)
    train, test = chronological_split(samples, 0.2)
    tok = RetrieverTokenizer(master, cfg)

    retriever, tok = train_retriever(train, master, cfg, tokenizer=tok)
    reranker = ShockFlowRecFormerReranker(cfg)
    reranker = train_reranker(retriever, reranker, train, master, tok, cfg)
    cutoff = max(s.cutoff for s in train).isoformat()
    index = build_index(retriever, master, tok, cutoff=cutoff)
    engine = RecommendationEngine(retriever, reranker, index, master, tok, cfg)

    test_eval = test[:E2E_EVAL_CAP]
    h1 = h3 = mrr = ndcg = feasible3 = no_feas = detour_sum = 0.0
    lat = []
    for s in test_eval:
        t0 = time.perf_counter()
        res, _ = engine.recommend(s, "eval")
        lat.append((time.perf_counter() - t0) * 1000)
        if res.no_feasible_candidate:
            no_feas += 1
            continue
        ids = [x.station_id for x in res.stations]
        feasible3 += 1.0 if all(x.feasible for x in res.stations) else 0.0
        detour_sum += sum(x.detour_km for x in res.stations) / len(res.stations)
        if s.chosen_station_id in ids:
            rank = ids.index(s.chosen_station_id) + 1
            h1 += 1.0 if rank == 1 else 0.0
            h3 += 1.0 if rank <= 3 else 0.0
            mrr += 1.0 / rank
            ndcg += 1.0 / math.log2(rank + 1)

    n = len(test_eval)
    lat.sort()
    p50 = lat[len(lat) // 2] if lat else 0.0
    p95 = lat[int(len(lat) * 0.95)] if lat else 0.0
    return {
        "source": source,
        "manifest": {
            "n_samples": len(samples), "n_train": len(train), "n_test": len(test),
            "n_test_eval": n, "rerank_train_cap": RERANK_TRAIN_CAP, "e2e_eval_cap": E2E_EVAL_CAP,
            "epochs": cfg.epochs, "num_stations": tok.num_stations,
        },
        "e2e": {
            "hit_rate_at_1": h1 / n, "hit_rate_at_3": h3 / n, "mrr": mrr / n, "ndcg_at_3": ndcg / n,
            "feasible_at_3_rate": feasible3 / n, "no_feasible_rate": no_feas / n,
            "avg_detour_km": detour_sum / n, "latency_p50_ms": p50, "latency_p95_ms": p95,
        },
        "event_ablation": "insufficient_event_overlap",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    args = ap.parse_args()
    if args.sample:
        trips, source = pd.read_csv(_SAMPLE), "fixture:citibike_sample.csv"
        cfg = RetrieverConfig(num_layers=1, epochs=1, batch_size=8, max_train_samples=12)
    else:
        trips, source = _load_real(), "real:JC-202606"
        cfg = RetrieverConfig(epochs=2, max_train_samples=4000)

    result = run(trips, source, cfg)
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    e = result["e2e"]
    print(f"source={result['source']}  test_eval={result['manifest']['n_test_eval']}")
    print(f"  E2E HitRate@1={e['hit_rate_at_1']:.3f} @3={e['hit_rate_at_3']:.3f} "
          f"MRR={e['mrr']:.3f} NDCG@3={e['ndcg_at_3']:.3f}")
    print(f"  feasible@3={e['feasible_at_3_rate']:.3f} no_feasible={e['no_feasible_rate']:.3f} "
          f"detour={e['avg_detour_km']:.3f}km  lat p50={e['latency_p50_ms']:.1f}ms "
          f"p95={e['latency_p95_ms']:.1f}ms")
    print(f"wrote {_OUT.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

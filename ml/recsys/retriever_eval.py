"""Measured ShockFlowRecFormerRetriever run on real Trip History (V1_Prompt §14).

Trains the dual encoder (bounded for CPU; caps logged) and reports exact Top-K retrieval metrics on
a chronological holdout, alongside the R0 nearest baseline for context. Event tokens do not overlap
plain June trip data, so R3(no-event) == R4(event): the event ablation records
``insufficient_event_overlap`` rather than a fabricated lift.

    python -m ml.recsys.retriever_eval           # real JC-202606
    python -m ml.recsys.retriever_eval --sample  # tiny fixture smoke
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

from config.recsys import RetrieverConfig

from .baselines import b0_nearest_feasible
from .candidates import generate_candidates
from .dataset import build_dataset, chronological_split
from .metrics import reciprocal_rank
from .retriever import build_index, evaluate_retriever, train_retriever
from .stations import build_station_master
from .tokenize import RetrieverTokenizer

_ROOT = Path(__file__).resolve().parents[2]
_REAL_ZIP = _ROOT / "data" / "raw" / "citibike" / "JC-202606-citibike-tripdata.csv.zip"
_SAMPLE = _ROOT / "data" / "fixtures" / "citibike_sample.csv"
_GBFS = _ROOT / "data" / "fixtures" / "gbfs_station_status.json"
_OUT = _ROOT / "reports" / "v1" / "recsys" / "retriever_metrics.json"

TEST_EVAL_CAP = 8000  # bound eval rows (logged, not silent)


def _load_real() -> pd.DataFrame:
    with zipfile.ZipFile(_REAL_ZIP) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv") and "MACOSX" not in n)
        with z.open(name) as f:
            return pd.read_csv(f)


def _b0_recall_at_20(test, master) -> float:
    hit = 0
    for s in test:
        cands = generate_candidates(s, master)
        ranked = b0_nearest_feasible(s, cands, master)
        if reciprocal_rank(ranked, s.chosen_station_id) > 0 and s.chosen_station_id in ranked[:20]:
            hit += 1
    return hit / len(test) if test else 0.0


def run(trips: pd.DataFrame, source: str, cfg: RetrieverConfig) -> dict:
    master = build_station_master(trips, gbfs_status_path=_GBFS)
    samples = build_dataset(trips)
    train, test = chronological_split(samples, 0.2)
    test_eval = test[:TEST_EVAL_CAP]

    tok = RetrieverTokenizer(master, cfg)
    model, tok = train_retriever(train, master, cfg, tokenizer=tok)
    cutoff = max(s.cutoff for s in train).isoformat()
    index = build_index(model, master, tok, cutoff=cutoff)
    train_chosen = {s.chosen_station_id for s in train}
    rep = evaluate_retriever(model, index, test_eval, master, tok, train_chosen, cfg)

    return {
        "source": source,
        "retriever_version": cfg.version,
        "manifest": {
            "n_trips": int(len(trips)),
            "n_samples": len(samples),
            "n_train": len(train),
            "n_train_used": min(len(train), cfg.max_train_samples),
            "max_train_samples": cfg.max_train_samples,
            "n_test": len(test),
            "n_test_eval": len(test_eval),
            "test_eval_cap": TEST_EVAL_CAP,
            "epochs": cfg.epochs,
            "num_stations": tok.num_stations,
        },
        "R4_retriever": rep.as_dict(),
        "R0_baseline_recall_at_20": _b0_recall_at_20(test_eval, master),
        "event_ablation": rep.event_status,  # R3 == R4 when no event overlap
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
        cfg = RetrieverConfig(epochs=2, max_train_samples=6000)

    result = run(trips, source, cfg)
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")

    m, r = result["manifest"], result["R4_retriever"]
    print(f"source={result['source']}  train_used={m['n_train_used']}  "
          f"test_eval={m['n_test_eval']}  stations={m['num_stations']}")
    print(f"  R4 retriever  R@5={r['recall_at_5']:.3f} R@10={r['recall_at_10']:.3f} "
          f"R@20={r['recall_at_20']:.3f} MRR@20={r['mrr_at_20']:.3f} NDCG@20={r['ndcg_at_20']:.3f}")
    print(f"  R0 nearest    R@20={result['R0_baseline_recall_at_20']:.3f}")
    print(f"  cold-start R@20={r['cold_start_recall_at_20']:.3f} (n={r['cold_start_n']})  "
          f"embed={r['embed_ms_per_query']:.2f}ms search={r['search_ms_per_query']:.3f}ms/q")
    print(f"  event_ablation={result['event_ablation']}")
    print(f"wrote {_OUT.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

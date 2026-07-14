"""V1-07A recommendation baseline evaluation on real Trip History (V1_Prompt §13).

Runs the RENT/RETURN dataset → candidate generation → baselines B0–B3 pipeline on real Citi Bike
data and reports measured ranking metrics. Deterministic given data + config + seed. Any bound
(MLP train cap) is logged, never silent (no-silent-truncation rule).

    python -m ml.recsys.evaluate            # real June zip -> reports/v1/recsys/metrics.json
    python -m ml.recsys.evaluate --sample   # tiny fixture (fast smoke)
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from config.recsys import RecsysConfig

from .baselines import b0_nearest_feasible, b1_distance_capacity, b2_distance_risk_benefit
from .candidates import generate_candidates
from .dataset import build_dataset, chronological_split
from .metrics import RankingReport, evaluate
from .mlp import MlpPairScorer
from .stations import build_station_master

_ROOT = Path(__file__).resolve().parents[2]
_REAL_ZIP = _ROOT / "data" / "raw" / "citibike" / "JC-202606-citibike-tripdata.csv.zip"
_SAMPLE = _ROOT / "data" / "fixtures" / "citibike_sample.csv"
_GBFS = _ROOT / "data" / "fixtures" / "gbfs_station_status.json"
_OUT = _ROOT / "reports" / "v1" / "recsys" / "metrics.json"

# Bound the MLP training rows so the run stays tractable; the drop is logged, not hidden.
MLP_TRAIN_SAMPLE_CAP = 8000


def _load_real() -> pd.DataFrame:
    with zipfile.ZipFile(_REAL_ZIP) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv") and "MACOSX" not in n)
        with z.open(name) as f:
            return pd.read_csv(f)


@dataclass
class Manifest:
    data_source: str
    n_trips: int
    n_samples: int
    n_train: int
    n_test: int
    mlp_train_cap: int
    mlp_train_used: int
    dropped_invalid_coord_note: str


def run(trips: pd.DataFrame, source: str, cfg: RecsysConfig | None = None) -> dict:
    cfg = cfg or RecsysConfig()
    master = build_station_master(trips, gbfs_status_path=_GBFS)
    samples = build_dataset(trips, cfg)
    train, test = chronological_split(samples, cfg.test_fraction)

    # B3 MLP: fit on a chronological head of train, capped for tractability (logged).
    mlp_train = train[:MLP_TRAIN_SAMPLE_CAP]
    scorer = MlpPairScorer(cfg).fit(mlp_train, master)

    rankers = {
        "B0_nearest_feasible": b0_nearest_feasible,
        "B1_distance_capacity": b1_distance_capacity,
        "B2_distance_risk_benefit": b2_distance_risk_benefit,
        "B3_mlp_pair_scorer": scorer.rank,
    }

    # Generate candidates once per test query; score with each ranker.
    test_cands = [(s, generate_candidates(s, master, cfg)) for s in test]
    reports: dict[str, RankingReport] = {}
    for name, ranker in rankers.items():
        cases = [(c, ranker(s, c, master), s.chosen_station_id) for s, c in test_cands]
        reports[name] = evaluate(cases)

    manifest = Manifest(
        data_source=source,
        n_trips=int(len(trips)),
        n_samples=len(samples),
        n_train=len(train),
        n_test=len(test),
        mlp_train_cap=MLP_TRAIN_SAMPLE_CAP,
        mlp_train_used=len(mlp_train),
        dropped_invalid_coord_note=(
            "Samples with NaN/out-of-range coords are skipped (see dataset._valid_coord)."
        ),
    )
    return {
        "config_version": cfg.version,
        "seed": cfg.seed,
        "manifest": manifest.__dict__,
        "metrics": {k: v.as_dict() for k, v in reports.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--sample", action="store_true", help="use the tiny fixture instead of real data"
    )
    args = ap.parse_args()

    if args.sample:
        trips, source = pd.read_csv(_SAMPLE), "fixture:citibike_sample.csv"
    else:
        trips, source = _load_real(), "real:JC-202606"

    result = run(trips, source)
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"source={source}  trips={result['manifest']['n_trips']}  "
          f"samples={result['manifest']['n_samples']}  test={result['manifest']['n_test']}")
    for name, m in result["metrics"].items():
        print(f"  {name:26s} HR@1={m['hit_rate_at_1']:.3f} HR@3={m['hit_rate_at_3']:.3f} "
              f"MRR={m['mrr']:.3f} NDCG@3={m['ndcg_at_3']:.3f} "
              f"cov={m['candidate_coverage']:.1f} inv_missing={m['inventory_missing_rate']:.2f}")
    print(f"wrote {_OUT.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

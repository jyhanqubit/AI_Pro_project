"""Run the clustered-switchback experiment battery (V1_Prompt §17).

Order per the prompt: A/A → recommendation-only → static vs dynamic credit → hybrid. All are
SIMULATED experiments (no real users): is_simulated=true, never a causal lift.

    python -m ml.experiment.evaluate   # -> reports/v1/experiments/switchback.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from config.experiment import ExperimentConfig
from config.pricing import POLICIES, PolicySpec
from ml.pricing.scenario import build_demo_scenario

from .engine import run_experiment

_ROOT = Path(__file__).resolve().parents[2]
_OUT = _ROOT / "reports" / "v1" / "experiments" / "switchback.json"

_P = {p.key: p for p in POLICIES}
_REC_ONLY = PolicySpec("REC", "Recommendation only", recommend=True)  # steering, no credit


def main() -> int:
    cfg = ExperimentConfig(n_clusters=4, n_time_blocks=10)
    stations = build_demo_scenario()

    battery = [
        ("AA", "A/A: identical arms -> effect should be ~0", _P["P0"], _P["P0"]),
        ("REC_ONLY", "Recommendation-only vs no action", _P["P0"], _REC_ONLY),
        ("STATIC_VS_DYNAMIC", "Static vs event-aware dynamic credit", _P["P2"], _P["P3"]),
        ("HYBRID", "Hybrid (truck+rec+dynamic) vs no action", _P["P0"], _P["P5"]),
    ]
    results = []
    for exp_id, hyp, control, treat in battery:
        r = run_experiment(exp_id, hyp, stations, {"control": control, "treatment": treat}, cfg)
        results.append(r)

    aa = results[0]
    payload = {
        "design": "clustered_switchback",
        "randomization_unit": "zone_cluster_x_time_block",
        "is_simulated": True,
        "disclaimer": "SIMULATED OUTCOME — NOT A LIVE BUSINESS RESULT",
        "config_version": cfg.version,
        "seed": cfg.seed,
        "aa_validation_passed": aa.itt_ci[0] <= 0.0 <= aa.itt_ci[1],
        "experiments": [r.as_dict() for r in results],
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"SIMULATED clustered-switchback battery (seed={cfg.seed})")
    print(f"A/A validation passed (CI contains 0): {payload['aa_validation_passed']}")
    print(f"{'experiment':22s} {'ITT':>8s}  {'95% CI':>18s}  {'CUPED':>8s}  SRM")
    for r in results:
        ci = f"[{r.itt_ci[0]:+.3f}, {r.itt_ci[1]:+.3f}]"
        print(f"{r.experiment_id:22s} {r.itt_effect:+8.4f}  {ci:>18s}  "
              f"{r.cuped_itt_effect:+8.4f}  {'ok' if r.srm_ok else 'FAIL'}")
    print(f"wrote {_OUT.relative_to(_ROOT)}  (SIMULATED — not a causal lift)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

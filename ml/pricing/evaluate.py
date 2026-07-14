"""Run the P0-P5 policy simulation and write the report (V1_Prompt §16).

    python -m ml.pricing.evaluate   # -> reports/v1/pricing/policy_sim.json

All outputs are SIMULATED (no real interaction log): is_simulated=true + disclaimer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from config.pricing import POLICIES, SIMULATED_DISCLAIMER, PricingConfig

from .policies import run_policy
from .scenario import build_demo_scenario

_ROOT = Path(__file__).resolve().parents[2]
_OUT = _ROOT / "reports" / "v1" / "pricing" / "policy_sim.json"


def main() -> int:
    cfg = PricingConfig()
    stations = build_demo_scenario()
    results = [run_policy(spec, stations, cfg) for spec in POLICIES]

    payload = {
        "mode": "policy_simulation",
        "is_simulated": True,
        "disclaimer": SIMULATED_DISCLAIMER,
        "config_version": cfg.version,
        "seed": cfg.seed,
        "budget": cfg.incentive_budget,
        "scenario": {
            "n_stations": len(stations),
            "total_rent_demand": sum(s.rent_demand for s in stations),
            "total_return_demand": sum(s.return_demand for s in stations),
        },
        "policies": [r.as_dict() for r in results],
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"SIMULATED policy comparison (seed={cfg.seed}, budget={cfg.incentive_budget})")
    print(f"{'policy':34s} fulfilled  short(min)  truck(km)  spend  net_cost  disparity")
    for r in results:
        print(f"{r.policy_key+' '+r.policy_label:34.34s} {r.fulfilled_demand_rate:8.3f}  "
              f"{r.shortage_minutes:9.0f}  {r.truck_bike_km:8.2f}  {r.incentive_spend:5.1f}  "
              f"{r.net_operating_cost:7.1f}  {r.service_disparity:8.3f}")
    print(f"wrote {_OUT.relative_to(_ROOT)}  ({SIMULATED_DISCLAIMER})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

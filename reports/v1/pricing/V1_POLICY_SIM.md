# V1-07D — Dynamic Incentive & Policy Simulation (SIMULATED)

> **SIMULATED OUTCOME — NOT A LIVE BUSINESS RESULT.** There is no real interaction log, so a
> versioned deterministic **choice simulator** stands in for rider behaviour. Every number below is
> `is_simulated=true`. No causal or business claim is made (V1_Prompt §16, invariant 10).

Reproduce: `make v1-policy-simulation` (writes `reports/v1/pricing/policy_sim.json`).

## Setup

- Scenario from the curated rebalancing fixture (`ml/pricing/scenario.py`): 5 Jersey City stations,
  **37 RENT + 29 RETURN** simulated riders over a 60-min horizon. Quiet zones hold surplus; the three
  event-exposed zones (Hoboken / City Hall / Newport) have raised rent demand → deficit.
- Dynamic pricing is a **pickup/return credit** (tiers `0, 0.5, 1, 1.5, 2, 3`), never a surcharge
  (credits ≥ 0). Budget is a **hard cap** (40 units). Constraints honoured: inventory, capacity,
  budget, max detour; fairness measured by **zone** only (no protected attributes).

## Simulated policy comparison (seed 42)

| Policy | Fulfilled | Shortage (min) | Truck (km) | Incentive spend | Net cost | Zone disparity |
|--------|-----------|----------------|-----------|-----------------|----------|----------------|
| P0 No action | 0.924 | 50 | 0.0 | 0.0 | 15.0 | 0.250 |
| **P1 Truck only** | 1.000 | 0 | 15.39 | 0.0 | **7.7** | 0.000 |
| P2 Static credit | 0.924 | 50 | 0.0 | 11.5 | 26.5 | 0.250 |
| P3 Event-aware dynamic credit | 1.000 | 0 | 0.0 | 40.0 (cap) | 40.0 | 0.000 |
| P4 Recommendation + dynamic credit | 1.000 | 0 | 0.0 | 40.0 (cap) | 40.0 | 0.000 |
| P5 Hybrid truck + rec + dynamic | 1.000 | 0 | 15.39 | 23.5 | 31.2 | 0.000 |

## Reading (simulated only)

- **In this scenario the truck (P1) is the cheapest way to full service** (net cost 7.7): a few
  well-chosen relocations remove the deficit outright. Pure incentive policies (P3/P4) also reach
  100% fulfilment but spend the whole budget, so their net cost is highest — credits move demand but
  don't add bikes.
- **Static credit (P2) is the worst active policy**: a flat credit is spent without shifting enough
  demand to close the shortage. Event-aware *dynamic* credit (P3) targets surplus stations and does
  close it.
- **Fairness**: P0/P2 leave a 0.25 zone disparity (event zones under-served); policies that reach
  full service also equalise it to 0.
- These are properties of a **modeled** choice simulator (fixed compliance = 0.6, credit weight =
  0.6, 10 min per unmet event). They are a decision-support comparison, **not** measured uplift, and
  would be replaced by a real clustered-switchback experiment (V1-08) once real users exist.

## Tested (`tests/unit/test_pricing.py`)

Credit tiers are the allowed non-negative set; the simulator **rejects negative credit** (no
surcharge); budget is a hard cap; the simulator is deterministic; P0 leaves shortage while an active
policy reduces it; fairness disparity is computed; truck-only uses no incentive. All results carry
`is_simulated=true` + the disclaimer.

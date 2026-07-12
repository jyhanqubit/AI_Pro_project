"""Demand-aggregation demo: ``python -m pipelines.features.demo [citibike_csv_or_zip]``.

Defaults to the offline Citi Bike sample fixture; pass a path to run on real data.
Backs the ``make build-features`` target (CLAUDE.md section 19).
"""

from __future__ import annotations

import sys
from pathlib import Path

from config.collectors import CITIBIKE_SAMPLE_FIXTURE
from pipelines.collectors import CitiBikeCollector
from pipelines.features import aggregate_demand, build_demand_features


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    source = Path(argv[0]) if argv else CITIBIKE_SAMPLE_FIXTURE

    print("ShockFlow AI - demand aggregation & feature store\n")
    print(f"source: {source}")

    trips = CitiBikeCollector(source).collect().records
    cells = aggregate_demand(trips)
    rows = build_demand_features(cells)

    zones = {c.zone_id for c in cells}
    print(
        f"trips={len(trips)}  demand_cells={len(cells)}  "
        f"feature_rows={len(rows)}  zones={len(zones)}"
    )

    if cells:
        busiest = max(cells, key=lambda c: c.departures)
        print(
            f"busiest cell: zone={busiest.zone_id} hour={busiest.hour_start.isoformat()} "
            f"dep={busiest.departures} arr={busiest.arrivals} net={busiest.net_flow}"
        )

    print("\nDone. Grain = H3 zone x local hour; features are leakage-safe (shifted).")


if __name__ == "__main__":
    main()

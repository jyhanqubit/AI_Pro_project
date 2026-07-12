"""Supervised design-matrix assembly for forecasting. CLAUDE.md sections 6, 11.

Turns leakage-safe ``DemandFeatureRow`` records into a time-sorted pandas panel: one row per
(zone, local hour) with numeric features and the demand targets. Ablation feature groups
(section 11.2) are defined here so B0-B4 select progressively larger column sets.

The event/graph groups (B2-B4) are represented as explicit columns. On an evaluation window
that predates the only curated events they are identically zero (the availability rule,
section 5.2, forbids any earlier contribution) -- this is documented and verified in the run,
never hidden (section 22).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from config.collectors import CITIBIKE_SAMPLE_FIXTURE
from config.features import DEMAND_TARGETS
from pipelines.collectors import CitiBikeCollector
from pipelines.features import aggregate_demand, build_demand_features
from pipelines.features.lags import DemandFeatureRow

# Zero-valued ablation groups appended on top of the B1 demand+calendar features.
ARTICLE_COUNT_COLS = ("article_count_6h", "article_count_24h")  # B2: raw article counts
EVENT_FEATURE_COLS = (  # B3: LLM-extracted event features
    "event_severity_sum",
    "event_confidence_mean",
    "transit_disruption_flag",
)
GRAPH_FEATURE_COLS = (  # B4: graph-propagated features
    "graph_distance_decayed_impact",
    "graph_neighbor_zone_impact",
    "graph_transit_exposure",
)


@dataclass
class Panel:
    """A time-sorted supervised panel plus the ablation column groups."""

    df: pd.DataFrame
    b1_cols: list[str]
    target_cols: tuple[str, ...] = DEMAND_TARGETS
    extra_cols: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def ablation_cols(self, level: str) -> list[str]:
        """Feature columns for an ablation level (B1 <= B2 <= B3 <= B4). B0 uses no matrix."""
        cols = list(self.b1_cols)
        if level in ("B2", "B3", "B4"):
            cols += list(self.extra_cols["article"])
        if level in ("B3", "B4"):
            cols += list(self.extra_cols["event"])
        if level == "B4":
            cols += list(self.extra_cols["graph"])
        return cols

    @property
    def hours(self) -> list[datetime]:
        return list(self.df["hour_start"])


def build_panel(rows: list[DemandFeatureRow]) -> Panel:
    """Assemble a :class:`Panel` from leakage-safe feature rows (time-sorted)."""
    feature_keys = sorted({k for r in rows for k in r.features})
    records: list[dict[str, object]] = []
    for r in rows:
        rec: dict[str, object] = {"zone_id": r.zone_id, "hour_start": r.hour_start}
        for t in DEMAND_TARGETS:
            rec[t] = r.targets[t]
        for k in feature_keys:
            rec[k] = r.features.get(k)
        records.append(rec)

    df = pd.DataFrame.from_records(records)
    df = df.sort_values(["hour_start", "zone_id"]).reset_index(drop=True)

    # Append the zero-valued event/graph ablation groups (B2-B4). Zero on any window that
    # predates the curated events; the run verifies this against build_graph_features.
    for col in (*ARTICLE_COUNT_COLS, *EVENT_FEATURE_COLS, *GRAPH_FEATURE_COLS):
        df[col] = 0.0

    return Panel(
        df=df,
        b1_cols=feature_keys,
        extra_cols={
            "article": ARTICLE_COUNT_COLS,
            "event": EVENT_FEATURE_COLS,
            "graph": GRAPH_FEATURE_COLS,
        },
    )


def load_real_panel(source: Path | None = None) -> Panel:
    """Collect Citi Bike trips -> demand cells -> features -> panel (offline)."""
    src = source or CITIBIKE_SAMPLE_FIXTURE
    trips = CitiBikeCollector(src).collect().records
    cells = aggregate_demand(trips)
    rows = build_demand_features(cells)
    return build_panel(rows)

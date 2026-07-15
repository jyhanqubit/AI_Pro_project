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
from typing import TYPE_CHECKING

import pandas as pd

from config.collectors import CITIBIKE_SAMPLE_FIXTURE
from config.features import DEMAND_TARGETS
from pipelines.collectors import CitiBikeCollector
from pipelines.features import aggregate_demand, build_demand_features
from pipelines.features.lags import DemandFeatureRow

if TYPE_CHECKING:
    from contracts.article import ArticleRecord
    from contracts.event import EventExtraction
    from pipelines.features import GraphFeatureConfig

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


def _snapshot_to_ablation_cols(features: dict[str, float]) -> dict[str, float]:
    """Map one as-of :class:`FeatureSnapshot` to the B2/B3/B4 panel columns (a pure projection)."""
    count_6h = sum(v for k, v in features.items() if k.startswith("event_count_6h_"))
    count_24h = sum(v for k, v in features.items() if k.startswith("event_count_24h_"))
    return {
        # B2 — raw news volume in the as-of window.
        "article_count_6h": float(count_6h),
        "article_count_24h": float(count_24h),
        # B3 — LLM-extracted event features.
        "event_severity_sum": float(features.get("source_weighted_severity", 0.0)),
        "event_confidence_mean": float(features.get("confidence_mean", 0.0)),
        "transit_disruption_flag": 1.0
        if features.get("event_count_6h_transit_disruption", 0.0) > 0
        else 0.0,
        # B4 — graph-propagated features.
        "graph_distance_decayed_impact": float(features.get("distance_decayed_impact", 0.0)),
        "graph_neighbor_zone_impact": float(features.get("neighbor_zone_impact", 0.0)),
        "graph_transit_exposure": float(features.get("transit_disruption_exposure", 0.0)),
    }


def _fill_event_columns(
    df: pd.DataFrame,
    events: list[EventExtraction],
    articles: list[ArticleRecord],
    *,
    config: GraphFeatureConfig | None = None,
) -> None:
    """Populate the B2/B3/B4 columns in ``df`` from real as-of graph features (leakage-safe).

    For every distinct target hour ``H`` the event/graph features are rebuilt **as-of H** with
    :func:`build_graph_features`, which enforces the availability rule (``available_at <= H``,
    §5.2). A ``(zone, H)`` row therefore only ever receives contributions from events already
    available at H — an event first available at 14:01 contributes exactly 0 to the 14:00 row.
    Zones/hours with no available event stay 0. Hours before the earliest event availability are
    skipped (all 0 by construction), which also keeps the pass cheap.
    """
    from pipelines.features import build_graph_features

    zero = {c: 0.0 for c in (*ARTICLE_COUNT_COLS, *EVENT_FEATURE_COLS, *GRAPH_FEATURE_COLS)}
    for col, val in zero.items():
        df[col] = val
    if not events:
        return

    earliest = min((e.available_at for e in events if e.available_at), default=None)
    zones = sorted(df["zone_id"].unique().tolist())
    # (zone_id, hour) -> row index, for a direct assignment without a per-row scan.
    index_by_key = {
        (z, h): i for i, (z, h) in enumerate(zip(df["zone_id"], df["hour_start"], strict=True))
    }

    for hour in sorted(df["hour_start"].unique()):
        cutoff = pd.Timestamp(hour).to_pydatetime()
        if earliest is not None and cutoff < earliest:
            continue  # nothing available yet -> columns stay 0 (leakage-safe + cheap)
        snaps = build_graph_features(
            events, articles, forecast_cutoff=cutoff, zones=zones, config=config
        )
        for s in snaps:
            key = (s.zone_id, hour)
            i = index_by_key.get(key)
            if i is None:
                continue
            for col, val in _snapshot_to_ablation_cols(s.features).items():
                df.at[i, col] = val


def build_panel(
    rows: list[DemandFeatureRow],
    *,
    events: list[EventExtraction] | None = None,
    articles: list[ArticleRecord] | None = None,
    graph_config: GraphFeatureConfig | None = None,
) -> Panel:
    """Assemble a :class:`Panel` from leakage-safe feature rows (time-sorted).

    When ``events``/``articles`` are supplied the B2-B4 ablation columns are filled from the real
    as-of graph features (leakage-safe); otherwise they are identically 0 (the honest default on any
    window that predates the events, verified in the run against ``build_graph_features``).
    """
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

    _fill_event_columns(df, events or [], articles or [], config=graph_config)

    return Panel(
        df=df,
        b1_cols=feature_keys,
        extra_cols={
            "article": ARTICLE_COUNT_COLS,
            "event": EVENT_FEATURE_COLS,
            "graph": GRAPH_FEATURE_COLS,
        },
    )


def load_real_panel(
    source: Path | None = None,
    *,
    news_source: Path | None = None,
    provider: str = "mock",
) -> Panel:
    """Collect Citi Bike trips -> demand cells -> features -> panel (offline).

    ``news_source`` (a JSONL article backfill) unlocks the real event ablation: its articles are
    extracted to events and joined into the B2-B4 columns as-of each target hour (leakage-safe). By
    default no news is joined, so B2-B4 == B1 (the honest zero-overlap baseline). To *measure* an
    LLM-feature lift, pass a news backfill whose availability overlaps the trip window.
    """
    src = source or CITIBIKE_SAMPLE_FIXTURE
    trips = CitiBikeCollector(src).collect().records
    cells = aggregate_demand(trips)
    rows = build_demand_features(cells)

    events: list = []
    articles: list = []
    if news_source is not None:
        from pipelines.collectors import NewsFixtureCollector
        from pipelines.events import build_provider, extract_events

        articles = NewsFixtureCollector(news_source).collect().records
        events, _ = extract_events(articles, build_provider(provider))
    return build_panel(rows, events=events, articles=articles)

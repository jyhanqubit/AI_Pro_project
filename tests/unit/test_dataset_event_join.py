"""As-of event/graph join into the forecasting panel (CLAUDE.md §5.2, §11.2, §17).

The forecasting ablation's B2-B4 columns must be populated from the real as-of graph features and
must obey the availability rule: an event first available at hour H contributes exactly 0 to every
row before H. These tests pin that leakage boundary on the deterministic demo events (transit
available 14:00, venue 15:00) so the real-data lift path cannot silently regress to hard-coded zero.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from config.collectors import NEWS_DEMO_FIXTURE
from ml.forecasting.dataset import (
    ARTICLE_COUNT_COLS,
    EVENT_FEATURE_COLS,
    GRAPH_FEATURE_COLS,
    _fill_event_columns,
)
from pipelines.collectors import NewsFixtureCollector
from pipelines.events import build_provider, extract_events

_ALL_COLS = (*ARTICLE_COUNT_COLS, *EVENT_FEATURE_COLS, *GRAPH_FEATURE_COLS)
_ZONE = "892a107216bffff"  # a demo transit-disruption zone


def _demo_events():
    articles = NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect().records
    events, _ = extract_events(articles, build_provider("mock"))
    return events, articles


def _frame(hours: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {"zone_id": [_ZONE] * len(hours), "hour_start": [datetime.fromisoformat(h) for h in hours]}
    )


def test_event_columns_are_zero_before_availability() -> None:
    events, articles = _demo_events()
    # 13:00 precedes the earliest event availability (transit 14:00).
    df = _frame(["2026-07-12T13:00:00-04:00"])
    _fill_event_columns(df, events, articles)
    for col in _ALL_COLS:
        assert df.at[0, col] == 0.0, f"{col} must be 0 before any event is available"


def test_event_columns_populate_after_availability() -> None:
    events, articles = _demo_events()
    df = _frame(["2026-07-12T14:00:00-04:00"])
    _fill_event_columns(df, events, articles)
    # The transit disruption is available at 14:00 -> its features must be live.
    assert df.at[0, "transit_disruption_flag"] == 1.0
    assert df.at[0, "graph_transit_exposure"] > 0.0
    assert df.at[0, "event_severity_sum"] > 0.0
    assert df.at[0, "article_count_24h"] > 0.0


def test_join_is_leakage_safe_across_the_boundary() -> None:
    events, articles = _demo_events()
    # Same zone at 13:00 and 14:00 in one frame: the 14:00 event must not leak into the 13:00 row.
    df = (
        _frame(["2026-07-12T13:00:00-04:00", "2026-07-12T14:00:00-04:00"])
        .sort_values("hour_start")
        .reset_index(drop=True)
    )
    _fill_event_columns(df, events, articles)
    assert all(df.at[0, c] == 0.0 for c in _ALL_COLS)  # 13:00 stays zero
    assert df.at[1, "transit_disruption_flag"] == 1.0  # 14:00 is live


def test_no_events_leaves_all_columns_zero() -> None:
    # The honest default: no news joined -> B2-B4 identically zero (== B1).
    df = _frame(["2026-07-12T14:00:00-04:00", "2026-07-12T16:00:00-04:00"])
    _fill_event_columns(df, [], [])
    for i in range(len(df)):
        assert all(df.at[i, c] == 0.0 for c in _ALL_COLS)

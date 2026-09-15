"""V2-01 H3 multi-holdout harness tests.

Locks the leakage-safety of the rolling-origin split and the window/aggregate helpers. The
leakage guard is the non-negotiable one (CLAUDE.md §5.4/§11.3): a test row's hour must never be
at or before the training frontier.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

from ml.forecasting.h3_multiholdout import (
    _agg,
    bounded_holdout,
    build_monthly_windows,
)

NY = ZoneInfo("America/New_York")


def _hours(start: datetime, n: int) -> list[datetime]:
    return [start.replace(hour=0) + __import__("datetime").timedelta(hours=i) for i in range(n)]


def test_bounded_holdout_is_leakage_safe():
    start = datetime(2024, 6, 1, tzinfo=NY)
    end = datetime(2024, 7, 1, tzinfo=NY)
    hours = _hours(datetime(2024, 5, 20, tzinfo=NY), 24 * 30)  # spans the boundary
    train_pos, test_pos = bounded_holdout(hours, start, end)
    assert train_pos.size > 0 and test_pos.size > 0
    # Every training hour is strictly before the test window; every test hour is inside it.
    assert max(hours[p] for p in train_pos) < start
    assert all(start <= hours[p] < end for p in test_pos)
    # No position appears in both sides.
    assert set(train_pos.tolist()).isdisjoint(test_pos.tolist())


def test_bounded_holdout_excludes_after_end():
    start = datetime(2024, 6, 1, tzinfo=NY)
    end = datetime(2024, 6, 15, tzinfo=NY)
    hours = _hours(datetime(2024, 5, 25, tzinfo=NY), 24 * 40)
    _, test_pos = bounded_holdout(hours, start, end)
    assert all(hours[p] < end for p in test_pos)  # rows after end are not in test


def test_build_monthly_windows_returns_last_n_and_skips_warmup():
    import pandas as pd

    hours = pd.Series(_hours(datetime(2024, 3, 8, tzinfo=NY), 24 * 176))  # ~Mar 8 -> late Aug
    windows = build_monthly_windows(hours, 3)
    assert len(windows) == 3
    # Consecutive, month-long, expanding-origin windows.
    for (s, e) in windows:
        assert s.day == 1 and e.day == 1
    starts = [s.month for s, _ in windows]
    assert starts == sorted(starts)  # chronological
    # March (the first, partial warm-up month) is never a test window.
    assert all(s.month != 3 for s, _ in windows)


def test_agg_ignores_nan_and_reports_spread():
    windows = [
        {"metrics": {"wape": 0.48}},
        {"metrics": {"wape": 0.50}},
        {"metrics": {"wape": float("nan")}},
        {"skipped": "empty"},
    ]
    agg = _agg(windows, "wape")
    assert agg["n"] == 2
    assert abs(agg["mean"] - 0.49) < 1e-9
    assert agg["std"] >= 0.0


def test_promoted_model_loader_manifest_only(tmp_path):
    import json

    from ml.forecasting.promoted import PromotedModelUnavailable, load_promoted_model

    # Missing manifest -> explicit error, never a silent demo fallback.
    try:
        load_promoted_model(tmp_path)
    except PromotedModelUnavailable:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected PromotedModelUnavailable")

    manifest = {
        "run_id": "run_v2-01_test",
        "claim_status": "measured",
        "freshness": "2026-07-20T00:00:00+00:00",
        "target": "departures",
        "algorithm": "hist_gradient_boosting",
    }
    (tmp_path / "promoted_model.json").write_text(json.dumps(manifest), encoding="utf-8")
    pm = load_promoted_model(tmp_path)  # no joblib present
    assert pm.run_id == "run_v2-01_test"
    assert pm.claim_status == "measured"
    assert pm.is_servable is False  # manifest without a fitted estimator is not servable

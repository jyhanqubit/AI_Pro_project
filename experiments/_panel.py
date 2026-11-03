"""Shared loader for experiments 2 and 3: the real Jersey City panel, cached as a pickle.

The promoted model was trained on ``data/raw/citibike`` (Jersey City archives, 2026-01..07,
226,953 usable rows / 219 zones per ``reports/v2/holdout/h3_multiholdout.json``). Building the
panel is deterministic but slow (pure-Python feature kernel), so the frame is pickled under
``data/processed/experiments/`` (git-ignored). The cache key is the sorted list of source files.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from ml.forecasting.dataset import load_real_panel, resolve_trip_sources
from ml.forecasting.experiment import usable_frame

DATA_DIR = Path("data/raw/citibike")
CACHE_DIR = Path("data/processed/experiments")


def panel_cache_path(data_dir: Path = DATA_DIR) -> Path:
    files = resolve_trip_sources(data_dir)
    key = hashlib.sha1("\n".join(p.name for p in files).encode()).hexdigest()[:10]
    return CACHE_DIR / f"panel_{key}.pkl"


def load_usable_panel(
    data_dir: Path = DATA_DIR, *, refresh: bool = False
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """(usable rows sorted by hour then zone, B1 feature columns, source file names)."""
    files = [p.name for p in resolve_trip_sources(data_dir)]
    cache = panel_cache_path(data_dir)
    meta = cache.with_suffix(".cols.txt")
    if cache.exists() and meta.exists() and not refresh:
        df = pd.read_pickle(cache)
        b1 = meta.read_text(encoding="utf-8").split()
        return df, b1, files
    panel = load_real_panel(data_dir)
    df = usable_frame(panel)
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_pickle(cache)
    meta.write_text("\n".join(panel.b1_cols), encoding="utf-8")
    return df, list(panel.b1_cols), files

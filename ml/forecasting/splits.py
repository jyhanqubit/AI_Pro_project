"""Temporal splits for forecasting evaluation. CLAUDE.md section 11.3.

Rolling-origin / expanding-window only. Every training fold ends strictly before its
validation window starts, so no future row informs a past prediction. Random K-fold is
forbidden here (section 11.3, section 22).
"""

from __future__ import annotations

from datetime import datetime

import numpy as np


def to_hour_index(hours: list[datetime]) -> np.ndarray:
    """Map aware hour_start timestamps to integer hour offsets from the earliest hour."""
    if not hours:
        return np.zeros(0, dtype=np.int64)
    epochs = np.array([int(h.timestamp()) for h in hours], dtype=np.int64)
    return (epochs - epochs.min()) // 3600


def final_holdout(hour_idx: np.ndarray, final_test_hours: int) -> tuple[np.ndarray, np.ndarray]:
    """Split row positions into (development, final-test) by an hour boundary.

    The final test is the latest ``final_test_hours`` hours; development is everything strictly
    before it. Returns position arrays into the original rows.
    """
    if hour_idx.size == 0:
        return np.zeros(0, dtype=int), np.zeros(0, dtype=int)
    boundary = hour_idx.max() - final_test_hours
    dev = np.where(hour_idx <= boundary)[0]
    test = np.where(hour_idx > boundary)[0]
    return dev, test


def rolling_origin_folds(
    hour_idx: np.ndarray, n_splits: int, cv_test_hours: int
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Expanding-window CV folds over positions within a development set.

    The last ``n_splits * cv_test_hours`` hours are cut into ``n_splits`` back-to-back
    validation windows; each fold trains on every row strictly before its window. Folds whose
    train side is empty are dropped. Positions index into ``hour_idx`` as given.
    """
    folds: list[tuple[np.ndarray, np.ndarray]] = []
    if hour_idx.size == 0:
        return folds
    dev_max = int(hour_idx.max())
    for j in range(n_splits):
        val_start = dev_max - (n_splits - j) * cv_test_hours + 1
        val_end = dev_max - (n_splits - j - 1) * cv_test_hours
        train_pos = np.where(hour_idx < val_start)[0]
        val_pos = np.where((hour_idx >= val_start) & (hour_idx <= val_end))[0]
        if train_pos.size == 0 or val_pos.size == 0:
            continue
        folds.append((train_pos, val_pos))
    return folds

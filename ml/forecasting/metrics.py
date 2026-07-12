"""Forecasting metrics. CLAUDE.md section 11.4.

Pure functions over numpy arrays. Zero-denominator behaviour is defined explicitly for WAPE
and MASE (section 11.4). Overall and event-window performance are reported separately.
"""

from __future__ import annotations

import numpy as np


def _arr(x: np.ndarray | list[float]) -> np.ndarray:
    return np.asarray(x, dtype=float)


def mae(y_true: np.ndarray | list[float], y_pred: np.ndarray | list[float]) -> float:
    """Mean absolute error."""
    yt, yp = _arr(y_true), _arr(y_pred)
    if yt.size == 0:
        return float("nan")
    return float(np.mean(np.abs(yt - yp)))


def wape(y_true: np.ndarray | list[float], y_pred: np.ndarray | list[float]) -> float:
    """Weighted absolute percentage error = sum|y - yhat| / sum|y|.

    Zero-denominator rule (section 11.4): if sum|y| == 0, return 0.0 when the error is also 0
    (a perfect trivial fit), else NaN (percentage undefined against an all-zero actual).
    """
    yt, yp = _arr(y_true), _arr(y_pred)
    denom = float(np.sum(np.abs(yt)))
    num = float(np.sum(np.abs(yt - yp)))
    if denom == 0.0:
        return 0.0 if num == 0.0 else float("nan")
    return num / denom


def seasonal_naive_scale(y_history: np.ndarray | list[float], period: int) -> float:
    """In-sample MAE of the seasonal naive (y_t vs y_{t-period}) — the MASE denominator.

    Returns NaN if there are too few points to form a single seasonal difference.
    """
    y = _arr(y_history)
    if y.size <= period:
        return float("nan")
    diffs = np.abs(y[period:] - y[:-period])
    scale = float(np.mean(diffs))
    return scale


def mase(
    y_true: np.ndarray | list[float],
    y_pred: np.ndarray | list[float],
    scale: float,
) -> float:
    """Mean absolute scaled error = MAE(model) / seasonal-naive in-sample MAE.

    ``scale`` must come from :func:`seasonal_naive_scale` on the training history (section 11.4:
    "Calculate MASE against an explicit seasonal naive scale"). Returns NaN if scale is 0/NaN.
    """
    if scale is None or not np.isfinite(scale) or scale == 0.0:
        return float("nan")
    return mae(y_true, y_pred) / scale


def peak_direction_accuracy(
    y_true: np.ndarray | list[float],
    y_pred: np.ndarray | list[float],
    y_prev: np.ndarray | list[float],
) -> float:
    """Fraction of rows where the predicted change direction vs the previous hour matches.

    Compares sign(yhat_t - y_{t-1}) with sign(y_t - y_{t-1}); a flat actual (sign 0) counts as
    correct only when the prediction is also flat. NaN if empty.
    """
    yt, yp, ypv = _arr(y_true), _arr(y_pred), _arr(y_prev)
    if yt.size == 0:
        return float("nan")
    true_dir = np.sign(yt - ypv)
    pred_dir = np.sign(yp - ypv)
    return float(np.mean(true_dir == pred_dir))


def forecast_delta_stability(
    baseline_pred: np.ndarray | list[float],
    event_aware_pred: np.ndarray | list[float],
) -> dict[str, float]:
    """Summarise the event-aware minus baseline forecast delta (section 11.4).

    Returns the mean absolute delta and its standard deviation. On a window with no available
    events the two predictions coincide and both are ~0 — an honest, informative result.
    """
    b, e = _arr(baseline_pred), _arr(event_aware_pred)
    delta = e - b
    if delta.size == 0:
        return {"mean_abs_delta": float("nan"), "std_delta": float("nan")}
    return {"mean_abs_delta": float(np.mean(np.abs(delta))), "std_delta": float(np.std(delta))}


def evaluate(
    y_true: np.ndarray | list[float],
    y_pred: np.ndarray | list[float],
    *,
    scale: float,
    y_prev: np.ndarray | list[float] | None = None,
    event_mask: np.ndarray | list[bool] | None = None,
) -> dict[str, float]:
    """Bundle the section 11.4 metrics; event-window WAPE is reported separately.

    ``event_window_wape`` is NaN when ``event_mask`` selects no rows (documented: on the June
    window the only curated events postdate the data, so no row falls in an event window).
    """
    out: dict[str, float] = {
        "wape": wape(y_true, y_pred),
        "mae": mae(y_true, y_pred),
        "mase": mase(y_true, y_pred, scale),
    }
    if y_prev is not None:
        out["peak_direction_accuracy"] = peak_direction_accuracy(y_true, y_pred, y_prev)
    if event_mask is not None:
        mask: np.ndarray = np.asarray(event_mask, dtype=bool)
        if mask.any():
            out["event_window_wape"] = wape(_arr(y_true)[mask], _arr(y_pred)[mask])
            out["event_window_n"] = float(int(mask.sum()))
        else:
            out["event_window_wape"] = float("nan")
            out["event_window_n"] = 0.0
    return out

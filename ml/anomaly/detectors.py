"""Anomaly detector families (V1_Prompt §12).

Each detector scans station-status observations and emits ``AnomalyAlert``s. Detectors are
deterministic and rule/statistics based (no fabricated incidents). ``is_synthetic_fault`` is carried
through from the observation so injected test faults stay distinguishable from real ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from config.anomaly import AnomalyConfig
from contracts.v1.anomaly import AnomalyAlert
from contracts.v1.enums import AnomalyType, ClaimState, OperatingModeV1, RootCauseStatus


@dataclass
class StationObs:
    station_id: str
    zone_id: str
    ts: datetime
    bikes: int
    docks: int
    capacity: int
    last_reported: datetime
    forecast: float | None = None
    actual: float | None = None
    is_synthetic_fault: bool = False


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _mad(xs: list[float], med: float) -> float:
    return _median([abs(x - med) for x in xs]) or 1.0


def _alert(
    detector: str, atype: AnomalyType, obs: StationObs, score: float, severity: float,
    root: RootCauseStatus, window_start: datetime, window_end: datetime,
    mode: OperatingModeV1,
) -> AnomalyAlert:
    return AnomalyAlert(
        anomaly_id=f"{detector}:{obs.station_id}:{int(obs.ts.timestamp())}",
        detector=detector,
        anomaly_type=atype,
        zone_id=obs.zone_id,
        station_id=obs.station_id,
        detected_at=obs.ts,
        window_start=window_start,
        window_end=window_end,
        score=round(score, 4),
        severity=round(min(1.0, max(0.0, severity)), 4),
        root_cause_status=root,
        is_synthetic_fault=obs.is_synthetic_fault,
        claim_state=ClaimState.MEASURED,
        mode=mode,
    )


def data_quality(obs: list[StationObs], cfg: AnomalyConfig, mode) -> list[AnomalyAlert]:
    out: list[AnomalyAlert] = []
    for o in obs:
        age_min = (o.ts - o.last_reported).total_seconds() / 60.0
        if age_min > cfg.freshness_max_minutes:
            out.append(_alert("freshness_rule", AnomalyType.DATA_QUALITY, o, age_min,
                              min(1.0, age_min / (cfg.freshness_max_minutes * 4)),
                              RootCauseStatus.LIKELY_DATA_QUALITY, o.last_reported, o.ts, mode))
        if o.bikes < 0 or o.docks < 0 or o.bikes > o.capacity or (o.bikes + o.docks) > o.capacity:
            out.append(_alert("capacity_rule", AnomalyType.DATA_QUALITY, o,
                              float(o.bikes + o.docks - o.capacity), 0.9,
                              RootCauseStatus.LIKELY_DATA_QUALITY, o.ts, o.ts, mode))
    return out


def inventory(history: dict[str, list[StationObs]], cfg: AnomalyConfig, mode) -> list[AnomalyAlert]:
    """Robust rolling z-score on bikes → sudden depletion/spike (inventory dislocation)."""
    out: list[AnomalyAlert] = []
    for series in history.values():
        series = sorted(series, key=lambda o: o.ts)
        for i in range(cfg.min_history, len(series)):
            window = [float(s.bikes) for s in series[max(0, i - cfg.rolling_window) : i]]
            med = _median(window)
            z = (series[i].bikes - med) / (1.4826 * _mad(window, med))
            if abs(z) >= cfg.depletion_z:
                o = series[i]
                out.append(_alert("rolling_zscore", AnomalyType.INVENTORY, o, z,
                                  min(1.0, abs(z) / (cfg.depletion_z * 2)),
                                  RootCauseStatus.INVENTORY_DISLOCATION,
                                  series[max(0, i - cfg.rolling_window)].ts, o.ts, mode))
    return out


def forecast_residual(obs: list[StationObs], cfg: AnomalyConfig, mode) -> list[AnomalyAlert]:
    out: list[AnomalyAlert] = []
    for o in obs:
        if o.forecast is None or o.actual is None:
            continue
        scale = max(cfg.residual_scale_floor, abs(o.forecast))
        ratio = abs(o.actual - o.forecast) / scale
        if ratio >= cfg.residual_sigma:
            out.append(_alert("residual_rule", AnomalyType.FORECAST_RESIDUAL, o, ratio,
                              min(1.0, ratio / (cfg.residual_sigma * 2)),
                              RootCauseStatus.UNEXPLAINED, o.ts, o.ts, mode))
    return out


def proxy_demand(obs: list[StationObs], cfg: AnomalyConfig, mode) -> list[AnomalyAlert]:
    """Optional Isolation Forest over (bikes, docks, fill-ratio). Off by default (§12)."""
    if not cfg.enable_isolation_forest:
        return []
    try:
        import numpy as np
        from sklearn.ensemble import IsolationForest
    except ImportError:
        return []
    if len(obs) < 8:
        return []
    x = np.array([[o.bikes, o.docks, o.bikes / max(1, o.capacity)] for o in obs], dtype=float)
    clf = IsolationForest(random_state=0, contamination="auto").fit(x)
    scores = -clf.score_samples(x)
    flags = clf.predict(x)
    out: list[AnomalyAlert] = []
    for o, s, f in zip(obs, scores, flags, strict=True):
        if f == -1:
            out.append(_alert("isolation_forest", AnomalyType.PROXY_DEMAND, o, float(s),
                              min(1.0, float(s)), RootCauseStatus.UNEXPLAINED, o.ts, o.ts, mode))
    return out


@dataclass
class DetectionResult:
    alerts: list[AnomalyAlert] = field(default_factory=list)


def detect_all(
    obs: list[StationObs],
    cfg: AnomalyConfig | None = None,
    mode: OperatingModeV1 = OperatingModeV1.LIVE_SHADOW,
) -> list[AnomalyAlert]:
    cfg = cfg or AnomalyConfig()
    history: dict[str, list[StationObs]] = {}
    for o in obs:
        history.setdefault(o.station_id, []).append(o)
    alerts = (
        data_quality(obs, cfg, mode)
        + inventory(history, cfg, mode)
        + forecast_residual(obs, cfg, mode)
        + proxy_demand(obs, cfg, mode)
    )
    return sorted(alerts, key=lambda a: (-a.severity, a.detected_at))


# convenience for window bounds in tests
def _window(ts: datetime, minutes: float) -> tuple[datetime, datetime]:
    return ts - timedelta(minutes=minutes), ts

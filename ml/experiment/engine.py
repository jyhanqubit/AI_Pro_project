"""Clustered-switchback experiment engine (V1_Prompt §17).

For each (zone-cluster × time-block) unit, the assigned arm's policy is run through the choice
simulator; outcomes are analysed with an ITT contrast and a **cluster** block-bootstrap CI (units
in a cluster are correlated). CUPED uses a pre-period (P0 no-action) covariate to cut variance.
Assignment is balanced (propensity 0.5). Results are **simulated** — never a causal lift.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

from config.experiment import ExperimentConfig
from config.pricing import POLICIES, PolicySpec, PricingConfig
from contracts.v1.experiment import ExposureLog, OutcomeLog
from ml.pricing.policies import run_policy
from ml.pricing.scenario import ScenarioStation

from .switchback import assignment_shares, switchback_assignment

_P0 = next(p for p in POLICIES if p.key == "P0")


def _unit_jitter(seed: int, cluster: str, t: int, jitter: float) -> float:
    h = int.from_bytes(hashlib.sha256(f"{seed}:{cluster}:{t}".encode()).digest()[:8], "big")
    return 1.0 + jitter * ((h / 2**64) * 2 - 1)  # 1 ± jitter


def _scale_demand(stations: list[ScenarioStation], factor: float) -> list[ScenarioStation]:
    return [
        replace(
            s,
            rent_demand=max(0, round(s.rent_demand * factor)),
            return_demand=max(0, round(s.return_demand * factor)),
        )
        for s in stations
    ]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


@dataclass
class ExperimentResult:
    experiment_id: str
    hypothesis: str
    status: str  # simulated_experiment | experiment_dry_run
    arms: tuple[str, str]
    n_units: int
    srm_ok: bool
    assignment_shares: dict[str, float]
    itt_effect: float
    itt_ci: tuple[float, float]
    cuped_itt_effect: float
    cuped_ci: tuple[float, float]
    is_simulated: bool = True
    disclaimer: str = "SIMULATED OUTCOME — NOT A LIVE BUSINESS RESULT"
    note: str = "Simulated ITT, not a real causal lift (no real users; §17)."
    exposure_logs: list[ExposureLog] = field(default_factory=list)
    outcome_logs: list[OutcomeLog] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d.pop("exposure_logs")
        d.pop("outcome_logs")
        d["n_exposure_logs"] = len(self.exposure_logs)
        d["n_outcome_logs"] = len(self.outcome_logs)
        return d


def _cluster_bootstrap_ci(
    per_cluster: dict[str, dict[str, list[float]]], cfg: ExperimentConfig, control: str, treat: str
) -> tuple[float, float]:
    """Percentile CI by resampling whole clusters (block bootstrap)."""
    clusters = sorted(per_cluster)
    rng = random.Random(cfg.seed + 1)
    effects: list[float] = []
    for _ in range(cfg.bootstrap_samples):
        sample = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        t_vals: list[float] = []
        c_vals: list[float] = []
        for cl in sample:
            t_vals += per_cluster[cl][treat]
            c_vals += per_cluster[cl][control]
        if t_vals and c_vals:
            effects.append(_mean(t_vals) - _mean(c_vals))
    if not effects:
        return (0.0, 0.0)
    effects.sort()
    lo = effects[int((cfg.alpha / 2) * len(effects))]
    hi = effects[min(len(effects) - 1, int((1 - cfg.alpha / 2) * len(effects)))]
    return (round(lo, 4), round(hi, 4))


def run_experiment(
    experiment_id: str,
    hypothesis: str,
    stations: list[ScenarioStation],
    arm_policies: dict[str, PolicySpec],
    cfg: ExperimentConfig | None = None,
    pricing_cfg: PricingConfig | None = None,
    status: str = "simulated_experiment",
) -> ExperimentResult:
    cfg = cfg or ExperimentConfig()
    arms = tuple(arm_policies.keys())
    if len(arms) != 2:
        raise ValueError("exactly two arms required (control, treatment)")
    control, treat = arms

    # Each zone-cluster is a self-contained sub-network that shares inventory (interference stays
    # within a cluster). The demo network is small, so clusters are replicate markets of the full
    # scenario with cluster-specific demand — this keeps the policy acting on a whole market while
    # still giving several clusters for the cluster-robust CI.
    cluster_ids = [f"cluster_{i}" for i in range(max(2, cfg.n_clusters))]
    by_cluster: dict[str, list[ScenarioStation]] = {c: list(stations) for c in cluster_ids}

    assignment = switchback_assignment(cluster_ids, cfg.n_time_blocks, arms, cfg.seed)

    exposure: list[ExposureLog] = []
    outcomes: list[OutcomeLog] = []
    # per_cluster[cluster][arm] = adjusted outcomes; raw kept for CUPED theta.
    raw: dict[str, dict[str, list[float]]] = {c: {control: [], treat: []} for c in cluster_ids}
    cov: dict[str, dict[str, list[float]]] = {c: {control: [], treat: []} for c in cluster_ids}
    t0 = datetime(2026, 6, 30, 0, 0, tzinfo=timezone(timedelta(hours=-4)))

    for c in cluster_ids:
        for t in range(cfg.n_time_blocks):
            if t < cfg.washout_blocks:  # washout: drop leading blocks
                continue
            arm = assignment[(c, t)]
            factor = _unit_jitter(cfg.seed, c, t, cfg.demand_jitter)
            unit_stations = _scale_demand(by_cluster[c], factor)
            if not unit_stations:
                continue
            outcome = run_policy(
                arm_policies[arm], unit_stations, pricing_cfg
            ).fulfilled_demand_rate
            covariate = run_policy(_P0, unit_stations, pricing_cfg).fulfilled_demand_rate
            unit_id = f"{c}:tb{t}"
            exposure.append(
                ExposureLog(experiment_id=experiment_id, unit_id=unit_id, arm=arm,
                            assigned_at=t0 + timedelta(hours=t), propensity=0.5)
            )
            outcomes.append(
                OutcomeLog(experiment_id=experiment_id, unit_id=unit_id, arm=arm,
                           metric_name="fulfilled_demand_rate", metric_value=outcome,
                           observed_at=t0 + timedelta(hours=t), is_simulated=True)
            )
            raw[c][arm].append(outcome)
            cov[c][arm].append(covariate)

    # SRM check: arm shares near 0.5.
    shares = assignment_shares(assignment, arms)
    srm_ok = all(abs(v - 0.5) <= cfg.srm_tolerance for v in shares.values())

    # ITT (unadjusted).
    all_t = [x for c in cluster_ids for x in raw[c][treat]]
    all_c = [x for c in cluster_ids for x in raw[c][control]]
    itt = round(_mean(all_t) - _mean(all_c), 4)
    itt_ci = _cluster_bootstrap_ci(raw, cfg, control, treat)

    # CUPED: adjust outcomes by theta*(covariate - mean_cov).
    flat_out = all_t + all_c
    flat_cov = [x for c in cluster_ids for x in cov[c][treat]] + [
        x for c in cluster_ids for x in cov[c][control]
    ]
    theta = _cuped_theta(flat_out, flat_cov)
    mean_cov = _mean(flat_cov)
    adj: dict[str, dict[str, list[float]]] = {
        c: {
            arm: [
                o - theta * (cv - mean_cov)
                for o, cv in zip(raw[c][arm], cov[c][arm], strict=True)
            ]
            for arm in arms
        }
        for c in cluster_ids
    }
    adj_t = [x for c in cluster_ids for x in adj[c][treat]]
    adj_c = [x for c in cluster_ids for x in adj[c][control]]
    cuped_itt = round(_mean(adj_t) - _mean(adj_c), 4)
    cuped_ci = _cluster_bootstrap_ci(adj, cfg, control, treat)

    return ExperimentResult(
        experiment_id=experiment_id, hypothesis=hypothesis, status=status, arms=arms,
        n_units=len(outcomes), srm_ok=srm_ok, assignment_shares=shares,
        itt_effect=itt, itt_ci=itt_ci, cuped_itt_effect=cuped_itt, cuped_ci=cuped_ci,
        exposure_logs=exposure, outcome_logs=outcomes,
    )


def _cuped_theta(outcomes: list[float], covariates: list[float]) -> float:
    n = len(outcomes)
    if n < 2:
        return 0.0
    mo, mc = _mean(outcomes), _mean(covariates)
    cov_oc = sum((o - mo) * (c - mc) for o, c in zip(outcomes, covariates, strict=True)) / n
    var_c = sum((c - mc) ** 2 for c in covariates) / n
    return cov_oc / var_c if var_c > 1e-12 else 0.0

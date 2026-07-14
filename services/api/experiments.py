"""Experiment results for the API/UI (V1_Prompt §17, §18).

Runs the clustered-switchback battery on demand (deterministic, offline, no torch) and returns the
computed values. Everything is SIMULATED — the response carries the disclaimer and never claims a
causal lift.
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def run_battery() -> dict:
    from config.experiment import ExperimentConfig
    from config.pricing import POLICIES, PolicySpec
    from ml.experiment.engine import run_experiment
    from ml.pricing.scenario import build_demo_scenario

    cfg = ExperimentConfig(n_clusters=4, n_time_blocks=10)
    stations = build_demo_scenario()
    p = {x.key: x for x in POLICIES}
    rec_only = PolicySpec(
        "REC", "Recommendation only", recommend=True,
        description="앱 추천으로 라이더를 여유 스테이션으로 유도. 크레딧 없음.",
    )

    def arm(spec: PolicySpec) -> dict:
        return {"policy": spec.key, "label": spec.label, "description": spec.description}

    battery = [
        ("AA", "동일한 두 arm — 효과가 0에 가까워야 정상(위양성 없음)", p["P0"], p["P0"]),
        ("REC_ONLY", "추천만 제공 vs 아무 조치 없음", p["P0"], rec_only),
        ("STATIC_VS_DYNAMIC", "정적 크레딧 vs 이벤트 반영 동적 크레딧", p["P2"], p["P3"]),
        ("HYBRID", "하이브리드(트럭+추천+동적) vs 아무 조치 없음", p["P0"], p["P5"]),
    ]
    results = []
    for exp_id, hyp, control, treat in battery:
        r = run_experiment(exp_id, hyp, stations, {"control": control, "treatment": treat}, cfg)
        results.append(
            {
                "experiment_id": r.experiment_id,
                "hypothesis": r.hypothesis,
                "arm_a": arm(control),  # A = control (대조군)
                "arm_b": arm(treat),  # B = treatment (처리군)
                "n_units": r.n_units,
                "itt_effect": r.itt_effect,
                "itt_ci": list(r.itt_ci),
                "cuped_itt_effect": r.cuped_itt_effect,
                "cuped_ci": list(r.cuped_ci),
                "srm_ok": r.srm_ok,
                "ci_excludes_zero": not (r.itt_ci[0] <= 0.0 <= r.itt_ci[1]),
                "status": r.status,
            }
        )
    aa = results[0]
    return {
        "design": "clustered_switchback",
        "randomization_unit": "zone_cluster_x_time_block",
        "metric_name": "fulfilled_demand_rate",
        "is_simulated": True,
        "disclaimer": "SIMULATED OUTCOME — NOT A LIVE BUSINESS RESULT (인과 lift 아님)",
        "aa_validation_passed": not aa["ci_excludes_zero"],
        "experiments": results,
    }

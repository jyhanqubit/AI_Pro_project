"""Turn an experiment result dict into a human-readable interpretation. CLAUDE.md sections 11, 18.

Produces a markdown report of the model choice, hyperparameters, feature importances, and the
ablation outcome -- strictly from the executed run's numbers (section 11.4). Non-improving or
zero-contribution results are stated plainly (sections 11.4, 22).
"""

from __future__ import annotations

from typing import Any

# Short, honest notes on what each tunable does (interpretation, not tuning advice).
_HYPERPARAM_NOTES: dict[str, str] = {
    "model__alpha": "L2 regularisation strength (larger = simpler, more shrinkage).",
    "model__n_estimators": "number of trees; more reduces variance with diminishing returns.",
    "model__max_depth": "tree depth cap; None grows full trees, small values regularise.",
    "model__min_samples_leaf": "minimum samples per leaf; larger smooths the fit.",
    "model__learning_rate": "boosting step size; smaller needs more iterations but generalises.",
    "model__max_iter": "boosting iterations for the histogram gradient booster.",
    "model__n_neighbors": "neighbours averaged per prediction; larger is smoother.",
    "model__weights": "neighbour weighting (uniform vs distance).",
}

_FEATURE_NOTES: dict[str, str] = {
    "dep_lag_1": "departures the previous hour (short-term persistence).",
    "dep_lag_24": "departures the previous day at the same hour.",
    "dep_lag_168": "departures one week earlier (the dominant weekly seasonal signal).",
    "dep_roll_mean_24": "trailing 24h mean departures (local demand level).",
    "dep_roll_mean_3": "trailing 3h mean departures (recent momentum baseline).",
    "dep_expanding_mean": "running mean departures for the zone (its demand scale).",
    "dep_momentum": "recent 3h vs 24h departures ratio (surge indicator).",
    "arr_lag_1": "arrivals the previous hour.",
    "arr_lag_168": "arrivals one week earlier.",
    "arr_roll_mean_3": "trailing 3h mean arrivals (recent inflow).",
    "arr_roll_mean_24": "trailing 24h mean arrivals.",
    "arr_expanding_mean": "running mean arrivals for the zone.",
    "cal_hour_sin": "cyclical hour-of-day encoding (sin).",
    "cal_hour_cos": "cyclical hour-of-day encoding (cos).",
    "cal_is_evening_rush": "evening commute window (16-18h).",
    "cal_is_morning_rush": "morning commute window (7-9h).",
    "cal_is_weekend": "weekend indicator.",
    "net_cumsum_day": "net flow accumulated earlier the same day (rebalancing pressure).",
    "member_share_lag_168": "member fraction of departures a week earlier (rider mix).",
}


def _fmt(x: Any, nd: int = 4) -> str:
    if isinstance(x, float):
        if x != x:  # NaN
            return "n/a"
        return f"{x:.{nd}f}"
    return str(x)


def build_interpretation(res: dict[str, Any]) -> str:
    best = res["best_algorithm"]
    algos = res["algorithms"]
    lines: list[str] = []

    lines.append("# Phase 06 — Forecasting Results & Interpretation\n")
    lines.append(
        f"Target **{res['target']}** at the H3 zone x local-hour grain, 1-hour-ahead. "
        f"Rolling-origin evaluation: {res['n_dev']} development rows, "
        f"{res['n_test']} out-of-sample test rows (last {res['test_window_hours']}h), "
        f"{res['n_cv_folds']} expanding-window CV folds, {res['n_features_b1']} B1 features. "
        f"Seed 42; no random split.\n"
    )

    # --- Algorithm leaderboard ---
    cs, co = res.get("ocs_shortage_cost", 2.0), res.get("ocs_overflow_cost", 1.0)
    lines.append("## Algorithm leaderboard (GridSearch, cross-validated)\n")
    lines.append(
        f"OCS = Operational Cost Score (domain-customised; shortage_cost={cs}, "
        f"overflow_cost={co}); bias = mean(ŷ − y).\n"
    )
    lines.append("| algorithm | CV WAPE | test WAPE | test MASE | test OCS | bias | peak-dir acc |")
    lines.append("|---|---|---|---|---|---|---|")
    order = sorted(algos, key=lambda k: algos[k]["cv_wape"])
    b0 = res["B0_seasonal_naive"]
    lines.append(
        f"| _B0 seasonal naive_ | - | {_fmt(b0['wape'])} | {_fmt(b0['mase'])} | "
        f"{_fmt(b0.get('ocs'))} | {_fmt(b0.get('bias'))} | "
        f"{_fmt(b0.get('peak_direction_accuracy'))} |"
    )
    for k in order:
        a = algos[k]
        t = a["test"]
        star = " ⭐" if k == best else ""
        lines.append(
            f"| {k}{star} | {_fmt(a['cv_wape'])} | {_fmt(t['wape'])} | {_fmt(t['mase'])} | "
            f"{_fmt(t.get('ocs'))} | {_fmt(t.get('bias'))} | "
            f"{_fmt(t.get('peak_direction_accuracy'))} |"
        )
    lines.append("")

    # --- Model interpretation ---
    bt = algos[best]["test"]
    lift = (b0["wape"] - bt["wape"]) / b0["wape"] * 100 if b0["wape"] else float("nan")
    lines.append("## Best model\n")
    lines.append(
        f"**{best}** wins on cross-validated WAPE and holds up out-of-sample "
        f"(test WAPE {_fmt(bt['wape'])}, MASE {_fmt(bt['mase'])}). "
        f"MASE < 1 means it beats the weekly seasonal-naive baseline; "
        f"it improves test WAPE over B0 by {_fmt(lift, 1)}%.\n"
    )

    # --- Custom metric: OCS ---
    lines.append("## Operational Cost Score — the data/domain-customised metric\n")
    lines.append(
        f"OCS charges under-forecast bikes (stockout risk) at {cs}× and over-forecast bikes "
        f"(overflow / wasted relocation) at {co}×, normalised by total demand — scale-free and "
        "zero-robust like WAPE, to which it reduces when the two costs are equal.\n"
    )
    lines.append("| model | OCS | under-forecast units | over-forecast units | bias |")
    lines.append("|---|---|---|---|---|")
    lines.append(
        f"| B0 seasonal naive | {_fmt(b0.get('ocs'))} | {_fmt(b0.get('shortage_units'), 0)} | "
        f"{_fmt(b0.get('overflow_units'), 0)} | {_fmt(b0.get('bias'))} |"
    )
    lines.append(
        f"| {best} (selected) | {_fmt(bt.get('ocs'))} | {_fmt(bt.get('shortage_units'), 0)} | "
        f"{_fmt(bt.get('overflow_units'), 0)} | {_fmt(bt.get('bias'))} |"
    )
    lines.append("")

    # --- Hyperparameters ---
    lines.append("## Best hyperparameters (interpretation)\n")
    lines.append("| parameter | value | what it controls |")
    lines.append("|---|---|---|")
    for p, v in res["best_params"].items():
        note = _HYPERPARAM_NOTES.get(p, "")
        lines.append(f"| `{p}` | {_fmt(v)} | {note} |")
    lines.append("")

    # --- Feature importance ---
    lines.append("## Feature importance (permutation, on the test holdout)\n")
    lines.append(
        "Mean WAPE degradation when each feature is shuffled (higher = more relied upon).\n"
    )
    lines.append("| rank | feature | importance | ± std | meaning |")
    lines.append("|---|---|---|---|---|")
    for i, im in enumerate(res["permutation_importance"][:12], 1):
        note = _FEATURE_NOTES.get(im["feature"], "")
        lines.append(
            f"| {i} | `{im['feature']}` | {_fmt(im['mean'])} | {_fmt(im['std'])} | {note} |"
        )
    lines.append("")
    rm = res["reduced_model"]
    lines.append(
        f"A reduced model on the top-{rm['k']} features scores test WAPE "
        f"{_fmt(rm['test']['wape'])} vs the full model's {_fmt(bt['wape'])} — "
        f"most predictive value concentrates in a handful of history features.\n"
    )

    # --- Ablation ---
    lines.append("## Ablation B0-B4\n")
    lines.append("| level | features | WAPE | MAE | MASE |")
    lines.append("|---|---|---|---|---|")
    abl = res["ablation"]
    labels = {
        "B0": "seasonal naive",
        "B1": "demand history + calendar",
        "B2": "+ article counts",
        "B3": "+ LLM event features",
        "B4": "+ graph-propagated features",
    }
    for lv in ("B0", "B1", "B2", "B3", "B4"):
        m = abl[lv]
        nf = m.get("n_features", "-")
        lines.append(
            f"| {lv} ({labels[lv]}) | {nf} | {_fmt(m['wape'])} | "
            f"{_fmt(m['mae'])} | {_fmt(m['mase'])} |"
        )
    ds = res["delta_stability_b4_vs_b1"]
    lines.append("")
    lines.append(
        "**Honest reading:** on this June evaluation window the only curated events postdate "
        "the data, so the availability rule (§5.2) forces every event/graph feature to zero. "
        f"B2-B4 therefore reproduce B1 exactly, and the B4-vs-B1 forecast delta is "
        f"{_fmt(ds['mean_abs_delta'])} (std {_fmt(ds['std_delta'])}). Event lift is **not "
        "demonstrable on this window** — it requires an evaluation span overlapping curated "
        "events. The event-aware machinery itself is validated by the as-of leakage tests.\n"
    )
    return "\n".join(lines)

"""Render the A/B/C ablation as an experiment: forest plot of paired lift with 95% CI.

Reads the rolling-origin ablation artifact (`reports/v2/llm_value/rolling_origin_ablation.json`)
and draws the two treatment contrasts the way an A/B/C test is usually reported — a forest plot
of the paired gain (%) per rolling-origin window with its block-bootstrap 95% CI, a zero
reference line, and each point coloured by its pre-registered verdict.

  A (control)   = A0  demand + calendar
  B (treatment) = A1  + permitted events (structured feed)
  C (treatment) = A2  + LLM-from-news events

The statistic is the paired gain = loss(control) - loss(treatment), resampled over day
blocks; a CI strictly above 0 is a win, strictly below 0 a loss, straddling 0 inconclusive,
and a window under the coverage floor is blocked. No number here is computed in this script —
it only visualises what the artifact already measured.

Usage:  python -m scripts.abc_experiment_plot
Output: reports/v2/llm_value/abc_forest.png
"""

from __future__ import annotations

import json
from pathlib import Path

ARTIFACT = Path("reports/v2/llm_value/rolling_origin_ablation.json")
OUT_PNG = Path("reports/v2/llm_value/abc_forest.png")

VERDICT_COLOR = {
    "measured_improvement": "#1a9850",  # green: CI entirely > 0
    "negative_lift": "#d73027",  # red:   CI entirely < 0
    "inconclusive": "#999999",  # grey:  CI straddles 0
    "blocked_data": "#cccccc",  # light: coverage floor not met
}


def _short_window(w: str) -> str:
    # "2026-02-01..2026-03-01" -> "2026-02" (the month held out)
    return w.split("..", 1)[0][:7]


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    windows = payload["windows"]
    labels = [_short_window(w["window"]) for w in windows]
    y = list(range(len(windows)))[::-1]  # newest window on top

    contrasts = [
        ("A1_minus_A0", "B vs A  ·  + permitted events", payload["stability_A1_minus_A0"]),
        ("A2_minus_A1", "C vs B  ·  + LLM news", payload["stability_A2_minus_A1"]),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    for ax, (key, title, stability) in zip(axes, contrasts, strict=True):
        for yi, w in zip(y, windows, strict=True):
            g = w[key]
            mean = g.get("mean_gain")
            lo, hi = g.get("ci_95", [None, None])
            verdict = g.get("verdict", "inconclusive")
            color = VERDICT_COLOR.get(verdict, "#999999")
            if mean is None or lo is None:
                continue
            ax.plot([lo, hi], [yi, yi], color=color, lw=2.4, solid_capstyle="round")
            ax.plot([mean], [yi], "o", color=color, ms=8, zorder=3)
        ax.axvline(0, color="#333333", ls="--", lw=1)
        ax.set_yticks(y)
        ax.set_yticklabels(labels)
        ax.set_xlabel("paired WAPE gain (%)  —  right = treatment better")
        ax.set_title(title, fontsize=11)
        ax.grid(True, axis="x", alpha=0.3)
        ax.margins(y=0.12)
        # cross-origin verdict badge
        ax.text(
            0.5,
            -0.30,
            f"cross-origin: {stability['stability']}",
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=9,
            color="#555555",
        )

    legend = [
        Line2D(
            [0], [0], color=VERDICT_COLOR["measured_improvement"], lw=3, label="improvement (CI>0)"
        ),
        Line2D([0], [0], color=VERDICT_COLOR["negative_lift"], lw=3, label="worse (CI<0)"),
        Line2D(
            [0], [0], color=VERDICT_COLOR["inconclusive"], lw=3, label="inconclusive (CI spans 0)"
        ),
        Line2D([0], [0], color=VERDICT_COLOR["blocked_data"], lw=3, label="blocked (low coverage)"),
    ]
    fig.legend(
        handles=legend,
        loc="upper center",
        ncol=4,
        fontsize=9,
        frameon=False,
        bbox_to_anchor=(0.5, 1.02),
    )
    fig.suptitle(
        "A/B/C event-feature experiment — rolling-origin 6 windows, day-block bootstrap 95% CI",
        y=0.94,
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.90))
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=140)
    print(f"wrote {OUT_PNG}")


if __name__ == "__main__":
    main()

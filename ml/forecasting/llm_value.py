"""V2-03 — LLM Incremental Value Ablation: ``python -m ml.forecasting.llm_value`` (make v2-llm-value).

The core V2 question: does the LLM event layer add value over a plain rule layer, after its own
cost? Three feature arms, identical cutoffs/splits, same (promoted) model — only the features
differ:

    A0  No-Event    : B1  demand history + calendar
    A1  Rule-Event  : B2  A0 + raw article-count features (keyword/volume, no structured extraction)
    A2  LLM-Event   : B4  A0 + LLM-extracted event features + graph-propagated features

For each rolling H3 holdout window every arm is refit with the promoted model and scored; the
incremental lift (A1−A0 rule value, A2−A1 LLM value) is reported with a block-bootstrap CI over
test days, translated to profit via the V2-02 ledger, and reported **net of an LLM cost estimate**.

Honest by construction: if A2 does not beat A1 the result is reported plainly (a null result is a
valid V2 outcome). No news is fabricated — the arms are built from whatever real, leakage-safe
overlapping news is supplied. The offline extractor is the deterministic mock (a stand-in for the
LLM structured-extraction path; a real LLM run is opt-in via ``--provider anthropic``); the mock's
actual cost is $0, and a real-LLM cost *estimate* (assumption-labeled) is included for net value.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config.forecasting import PRIMARY_TARGET
from contracts.v2.ledger import LedgerAssumptions
from ml.forecasting.baselines import seasonal_naive_predict
from ml.forecasting.dataset import Panel, load_real_panel
from ml.forecasting.experiment import _EVENT_SIGNAL_COLS, usable_frame
from ml.forecasting.h3_multiholdout import _fit_promoted, bounded_holdout, build_monthly_windows
from ml.forecasting.metrics import mae, wape
from optimization.ledger import account
from optimization.ledger_run import load_assumptions

OUT_DIR = Path("reports/v2/llm_value")
PROMOTED_PATH = Path("reports/v2/holdout/promoted_model.json")
ARMS = {"A0_no_event": "B1", "A1_rule_event": "B2", "A2_llm_event": "B4"}
# LLM cost estimate assumptions (clearly labeled; a real run's cost depends on provider/model).
CHARS_PER_TOKEN = 4.0
LLM_PRICE_PER_MTOK_ASSUMPTION = 0.30  # USD per 1M input tokens (assumption; cheap-tier model)


def _event_mask(df: pd.DataFrame) -> np.ndarray:
    cols = [c for c in _EVENT_SIGNAL_COLS if c in df.columns]
    if not cols:
        return np.zeros(len(df), dtype=bool)
    return (df[cols].abs().sum(axis=1).to_numpy() > 0)


def _arm_predictions(
    df: pd.DataFrame, panel: Panel, target: str, promoted: dict[str, Any],
    windows: list[tuple[datetime, datetime]],
) -> dict[str, Any]:
    """Refit the promoted model per arm per window; return pooled test arrays + per-window WAPE."""
    y = df[target].to_numpy(dtype=float)
    hours = list(df["hour_start"])
    ev_mask_all = _event_mask(df)

    pooled: dict[str, Any] = {"y_true": [], "day": [], "event": [], "preds": {a: [] for a in ARMS}}
    per_window: list[dict[str, Any]] = []

    for i, (start, end) in enumerate(windows):
        train_pos, test_pos = bounded_holdout(hours, start, end)
        if train_pos.size == 0 or test_pos.size == 0:
            continue
        assert max(hours[p] for p in train_pos) < start, "leakage!"
        y_tr, y_te = y[train_pos], y[test_pos]
        scale = mae(y_tr, seasonal_naive_predict(df.iloc[train_pos], target))
        win: dict[str, Any] = {"window_id": i, "test_start": start.isoformat(), "n_test": int(test_pos.size)}
        for arm, level in ARMS.items():
            cols = panel.ablation_cols(level)
            x = df[cols].to_numpy(dtype=float)
            est = _fit_promoted(promoted["algorithm"], promoted["params"])
            est.fit(x[train_pos], y_tr)
            pred = np.asarray(est.predict(x[test_pos]), dtype=float)
            win[arm] = {"wape": wape(y_te, pred), "n_features": len(cols)}
            if arm == list(ARMS)[0]:
                pooled["y_true"].append(y_te)
                days = pd.to_datetime(pd.Series([hours[p] for p in test_pos])).dt.strftime("%Y-%m-%d").to_numpy()
                pooled["day"].append(days)
                pooled["event"].append(ev_mask_all[test_pos])
            pooled["preds"][arm].append(pred)
        per_window.append(win)
    for k in ("y_true", "day", "event"):
        pooled[k] = np.concatenate(pooled[k]) if pooled[k] else np.array([])
    for a in ARMS:
        pooled["preds"][a] = np.concatenate(pooled["preds"][a]) if pooled["preds"][a] else np.array([])
    return {"per_window": per_window, "pooled": pooled}


def _bootstrap_wape_delta(
    y: np.ndarray, pa: np.ndarray, pb: np.ndarray, days: np.ndarray, *, n: int = 2000, seed: int = 42
) -> dict[str, float]:
    """Block-bootstrap CI for WAPE(b) − WAPE(a) resampling whole test days (lower WAPE = better)."""
    rng = np.random.default_rng(seed)
    uniq = np.unique(days)
    idx_by_day = {d: np.where(days == d)[0] for d in uniq}
    deltas = np.empty(n)
    for b in range(n):
        pick = rng.choice(uniq, size=uniq.size, replace=True)
        rows = np.concatenate([idx_by_day[d] for d in pick])
        deltas[b] = wape(y[rows], pb[rows]) - wape(y[rows], pa[rows])
    lo, hi = np.percentile(deltas, [2.5, 97.5])
    point = float(wape(y, pb) - wape(y, pa))
    return {"delta_wape": point, "ci_lo": float(lo), "ci_hi": float(hi)}


def _verdict(delta_ci: dict[str, float]) -> str:
    """A2−A1 (or A1−A0) WAPE delta: negative = improvement. Verdict from the CI sign."""
    if delta_ci["ci_hi"] < 0:
        return "measured_improvement"
    if delta_ci["ci_lo"] > 0:
        return "measured_regression"
    return "no_measurable_lift"


def _llm_cost(news_path: Path | None) -> dict[str, Any]:
    """Actual mock cost = $0; a real-LLM extraction cost *estimate* (assumption) for net value."""
    n_articles, n_chars = 0, 0
    if news_path and news_path.exists():
        for line in news_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            n_articles += 1
            n_chars += len(r.get("title", "")) + len(r.get("text", ""))
    est_tokens = n_chars / CHARS_PER_TOKEN
    est_usd = est_tokens / 1_000_000 * LLM_PRICE_PER_MTOK_ASSUMPTION
    return {
        "provider": "mock",
        "actual_usd": 0.0,
        "n_articles": n_articles,
        "estimated_input_tokens": round(est_tokens),
        "price_per_mtok_assumption": LLM_PRICE_PER_MTOK_ASSUMPTION,
        "estimated_real_usd": round(est_usd, 4),
        "basis": "chars/4 tokens * assumed cheap-tier input price; real cost depends on provider/model",
    }


def run_ablation(panel: Panel, promoted: dict[str, Any], target: str, news_path: Path | None,
                 A: LedgerAssumptions, stamp: datetime) -> dict[str, Any]:
    df = usable_frame(panel)
    windows = build_monthly_windows(df["hour_start"], 3)
    res = _arm_predictions(df, panel, target, promoted, windows)
    pooled = res["pooled"]
    y, days, ev = pooled["y_true"], pooled["day"], pooled["event"]
    preds = pooled["preds"]

    # Overall + event-window WAPE per arm.
    arms_summary = {}
    for a in ARMS:
        p = preds[a]
        arms_summary[a] = {
            "wape": float(wape(y, p)),
            "event_window_wape": float(wape(y[ev], p[ev])) if ev.any() else None,
            "net_profit_simulated": account(np.rint(p), y, baseline_stock=np.rint(p), assumptions=A).net,
        }

    # Incremental lift with block-bootstrap CI (WAPE delta; negative = improvement).
    lift = {
        "rule_over_none_A1_minus_A0": _bootstrap_wape_delta(y, preds["A0_no_event"], preds["A1_rule_event"], days),
        "llm_over_rule_A2_minus_A1": _bootstrap_wape_delta(y, preds["A1_rule_event"], preds["A2_llm_event"], days),
        "llm_over_none_A2_minus_A0": _bootstrap_wape_delta(y, preds["A0_no_event"], preds["A2_llm_event"], days),
    }
    for k in lift:
        lift[k]["verdict"] = _verdict(lift[k])

    cost = _llm_cost(news_path)
    profit_lift_llm_over_rule = round(
        arms_summary["A2_llm_event"]["net_profit_simulated"] - arms_summary["A1_rule_event"]["net_profit_simulated"], 2
    )
    net_llm_value = round(profit_lift_llm_over_rule - cost["estimated_real_usd"], 2)

    # Did the event features actually change any prediction? If A2 == A0 bitwise, the LLM features
    # carried no signal into the model on this slice — an honest "insufficient overlap", not a
    # measured null with variance. Distinguish the two explicitly.
    arms_identical = bool(np.allclose(preds["A2_llm_event"], preds["A0_no_event"]))
    test_cov = float(ev.mean()) if y.size else 0.0
    if arms_identical or test_cov == 0.0:
        claim = "blocked_data"
        headline = "insufficient_event_overlap"
    else:
        claim = "measured"
        headline = lift["llm_over_rule_A2_minus_A1"]["verdict"]

    return {
        "run_id": f"run_v2-03_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/llm_value/incremental_value.json",
        "mode": "historical_replay",
        "claim_status": claim,
        "freshness": stamp.isoformat(),
        "target": target,
        "grain": "h3_zone_x_local_hour",
        "promoted_model": {"algorithm": promoted.get("algorithm"), "run_id": promoted.get("run_id")},
        "arms": arms_summary,
        "n_decisions": int(y.size),
        "event_window_rows": int(ev.sum()),
        "event_coverage_fraction": round(test_cov, 6),
        "arms_identical_on_test": arms_identical,
        "incremental_lift_wape": lift,
        "llm_cost": cost,
        "profit_lift_llm_over_rule_simulated": profit_lift_llm_over_rule,
        "net_llm_value_simulated": net_llm_value,
        "assumption_set_version": A.version,
        "per_window": res["per_window"],
        "headline_verdict": headline,
        "note": (
            "Arms share cutoffs/splits and the promoted model; only features differ. WAPE delta<0 = "
            "improvement. Profit is simulated (assumption-conditioned); LLM actual cost is $0 (mock), "
            "with an assumption-labeled real-LLM cost estimate for net value. arms_identical_on_test "
            "== true means the extracted events carried no signal into the test windows (the real, "
            "geo-matched overlapping event volume is negligible on this JC/2026 slice) -> "
            "insufficient_event_overlap, reported honestly. This is the same gap v1 flagged, now "
            "shown with the full 3-arm + CI + cost framework. Path to unblock: trip+news of the same "
            "geography/period at sufficient event density (e.g. NYC-wide trips + NYC news, or "
            "JC-specific event collection)."
        ),
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="ml.forecasting.llm_value")
    ap.add_argument("--data-dir", default="data/raw/citibike_2026")
    ap.add_argument("--news", default="data/fixtures/news_live/news_gdelt_nyc_2026h1.jsonl",
                    help="ArticleRecord JSONL news backfill overlapping the trip window")
    ap.add_argument("--provider", choices=("mock", "anthropic"), default="mock")
    ns = ap.parse_args(argv)
    stamp = datetime.now(UTC)

    if not PROMOTED_PATH.exists():
        raise SystemExit(f"{PROMOTED_PATH} missing — run `make v2-holdout` (V2-01) first.")
    promoted = json.loads(PROMOTED_PATH.read_text(encoding="utf-8"))
    target = promoted.get("target", PRIMARY_TARGET)
    A = load_assumptions()

    news_path = Path(ns.news)
    print(f"V2-03 LLM value ablation — arms={list(ARMS)}  news={news_path}  provider={ns.provider}")
    panel = load_real_panel(Path(ns.data_dir), news_source=news_path if news_path.exists() else None,
                            provider=ns.provider)
    report = run_ablation(panel, promoted, target, news_path if news_path.exists() else None, A, stamp)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "incremental_value.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\ndecisions={report['n_decisions']}  event rows={report['event_window_rows']} "
          f"(coverage {report['event_coverage_fraction']*100:.3f}%)  claim_status={report['claim_status']}")
    for a, s in report["arms"].items():
        ew = s["event_window_wape"]
        print(f"  {a:16s} WAPE={s['wape']:.4f}  event_wape={('%.4f'%ew) if ew is not None else 'n/a'}  "
              f"net(sim)={s['net_profit_simulated']:.0f}")
    for k, v in report["incremental_lift_wape"].items():
        print(f"  {k}: dWAPE={v['delta_wape']:+.4f} CI[{v['ci_lo']:+.4f},{v['ci_hi']:+.4f}] -> {v['verdict']}")
    print(f"LLM cost: actual ${report['llm_cost']['actual_usd']} (mock); est real "
          f"${report['llm_cost']['estimated_real_usd']} ({report['llm_cost']['n_articles']} articles)")
    print(f"profit lift A2 vs A1 (sim): {report['profit_lift_llm_over_rule_simulated']}  "
          f"net LLM value (sim): {report['net_llm_value_simulated']}")
    print(f"HEADLINE: {report['headline_verdict']}")
    print(f"report: {OUT_DIR}/incremental_value.json")


if __name__ == "__main__":
    main()

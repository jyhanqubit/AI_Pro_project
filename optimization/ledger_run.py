"""V2-02 — Profit / Regret Ledger runner: ``python -m optimization.ledger_run`` (make v2-ledger).

Translates the V2-01 promoted forecast into money. For each rolling H3 holdout window it turns
three stocking policies into a profit/regret ledger and compares them:

    no_action       : stock at the seasonal-naive baseline (status quo, no model)
    promoted_model  : stock at the V2-01 promoted forecast (the measured model)
    oracle          : stock at the realized demand (perfect-foresight upper bound)

This is the "predictive lift -> profit/regret" evidence (addendum required-evidence #4): if the
model's net beats no-action, the forecast accuracy is worth money; regret vs Oracle shows the
remaining headroom.

Scope (honest): V2-02 is single-period **stocking** economics — margin on realized rentals minus
shortage externality minus overflow cost. **Relocation is zero here** (no repositioning modeled;
the ledger supports it but the geography-aware origin->destination moves belong to V2-04 MPC).
The unit counts are measured; the dollar conversion is assumption-conditioned
(`config/v2/assumptions.yaml`), so the dollar outputs are labeled `simulated` and a sensitivity
sweep is included.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from config.forecasting import PRIMARY_TARGET
from contracts.v2.ledger import LedgerAssumptions
from ml.forecasting.dataset import load_real_panel
from ml.forecasting.experiment import usable_frame
from ml.forecasting.h3_multiholdout import build_monthly_windows, predict_windows
from optimization.ledger import account, oracle_stock, regret

ASSUMPTIONS_PATH = Path("config/v2/assumptions.yaml")
PROMOTED_PATH = Path("reports/v2/holdout/promoted_model.json")
OUT_DIR = Path("reports/v2/ledger")


def load_assumptions(path: Path = ASSUMPTIONS_PATH) -> LedgerAssumptions:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return LedgerAssumptions.model_validate(data)


def _pooled(preds: list[dict[str, Any]], key: str) -> np.ndarray:
    return np.concatenate([p[key] for p in preds]) if preds else np.zeros(0)


def _ledger_for(stock: np.ndarray, actual: np.ndarray, A: LedgerAssumptions, policy: str,
                oracle_net: float | None = None) -> dict[str, Any]:
    # baseline_stock == stock => zero relocation in the single-period V2-02 model (see module doc).
    comp = account(stock, actual, baseline_stock=stock, assumptions=A)
    d = comp.as_dict()
    d["policy"] = policy
    if oracle_net is not None:
        d["regret_vs_oracle"] = round(oracle_net - comp.net, 6)
    return d


def _sensitivity(model: np.ndarray, base: np.ndarray, actual: np.ndarray,
                 A: LedgerAssumptions) -> list[dict[str, Any]]:
    """Sign-robustness of (model net − no_action net) as the two cost assumptions vary."""
    out: list[dict[str, Any]] = []
    for se in (A.shortage_externality * 0.5, A.shortage_externality, A.shortage_externality * 2.0):
        for op in (A.overflow_penalty * 0.5, A.overflow_penalty, A.overflow_penalty * 2.0):
            A2 = A.model_copy(update={"shortage_externality": se, "overflow_penalty": op})
            m = account(model, actual, baseline_stock=model, assumptions=A2).net
            b = account(base, actual, baseline_stock=base, assumptions=A2).net
            out.append({"shortage_externality": round(se, 4), "overflow_penalty": round(op, 4),
                        "model_minus_no_action_net": round(m - b, 4)})
    return out


def main(argv: list[str] | None = None) -> None:
    stamp = datetime.now(UTC)
    A = load_assumptions()
    print(f"assumption set: {A.version} (sourced={A.sourced})  oracle_upper_bound={A.oracle_is_upper_bound}")
    if not PROMOTED_PATH.exists():
        raise SystemExit(f"{PROMOTED_PATH} missing — run `make v2-holdout` (V2-01) first.")
    promoted = json.loads(PROMOTED_PATH.read_text(encoding="utf-8"))
    target = promoted.get("target", PRIMARY_TARGET)

    panel = load_real_panel(Path(promoted.get("data_source", "data/raw/citibike")))
    df = usable_frame(panel)
    windows = build_monthly_windows(df["hour_start"], 3)
    preds = predict_windows(df, panel.b1_cols, target, promoted, windows)
    if not preds:
        raise SystemExit("no window predictions — check the panel / windows")

    actual = _pooled(preds, "actual")
    model = np.rint(_pooled(preds, "model"))
    base = np.rint(_pooled(preds, "seasonal_naive"))
    oracle_s = oracle_stock(actual, A)

    oracle_led = _ledger_for(oracle_s, actual, A, "oracle")
    oracle_net = oracle_led["net"]
    oracle_led["regret_vs_oracle"] = 0.0
    no_action = _ledger_for(base, actual, A, "no_action", oracle_net)
    model_led = _ledger_for(model, actual, A, "promoted_model", oracle_net)

    # Oracle is a clean upper bound in the no-relocation single-period model: regret must be >= 0.
    for pol in (no_action, model_led):
        assert pol["regret_vs_oracle"] >= -1e-6, f"negative regret for {pol['policy']} — bug"

    lift_net = round(model_led["net"] - no_action["net"], 4)
    per_window = []
    for p in preds:
        a, m, bs = p["actual"], np.rint(p["model"]), np.rint(p["seasonal_naive"])
        onet = account(oracle_stock(a, A), a, baseline_stock=oracle_stock(a, A), assumptions=A).net
        mnet = account(m, a, baseline_stock=m, assumptions=A).net
        bnet = account(bs, a, baseline_stock=bs, assumptions=A).net
        per_window.append({
            "window_id": p["window_id"], "test_start": p["test_start"],
            "model_net": round(mnet, 2), "no_action_net": round(bnet, 2),
            "oracle_net": round(onet, 2), "model_lift_net": round(mnet - bnet, 2),
            "model_regret": round(onet - mnet, 2),
        })

    report = {
        "run_id": f"run_v2-02_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/ledger/profit_regret.json",
        "mode": "historical_replay",
        "claim_status": "simulated",  # unit counts measured; $ conversion assumption-conditioned
        "freshness": stamp.isoformat(),
        "assumption_set_version": A.version,
        "assumptions_sourced": A.sourced,
        "model_grain": "h3_zone_x_local_hour",
        "target": target,
        "scope_note": "single-period stocking economics; relocation=0 (deferred to V2-04)",
        "promoted_model": {"algorithm": promoted.get("algorithm"), "run_id": promoted.get("run_id")},
        "n_decisions": int(actual.size),
        "by_policy": {
            "no_action": no_action,
            "promoted_model": model_led,
            "oracle": oracle_led,
        },
        "predictive_lift_to_profit": {
            "model_minus_no_action_net": lift_net,
            "model_regret_vs_oracle": model_led["regret_vs_oracle"],
            "interpretation": (
                "positive model_minus_no_action_net = the promoted forecast is worth money vs the "
                "seasonal-naive status quo; model_regret_vs_oracle = remaining headroom to perfect foresight"
            ),
        },
        "per_window": per_window,
        "sensitivity_model_minus_no_action_net": _sensitivity(model, base, actual, A),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "profit_regret.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"decisions (zone-hours): {actual.size}")
    for name, led in report["by_policy"].items():
        print(f"  {name:14s} net={led['net']:>12.2f}  short_u={led['shortage_units']:>9.0f}  "
              f"over_u={led['overflow_units']:>9.0f}  regret={led['regret_vs_oracle']:>10.2f}")
    print(f"\npredictive lift -> profit: model beats no-action by {lift_net:.2f} "
          f"(assumption set {A.version}); regret vs oracle {model_led['regret_vs_oracle']:.2f}")
    sens = report["sensitivity_model_minus_no_action_net"]
    signs = {int(np.sign(s["model_minus_no_action_net"])) for s in sens}
    print(f"sensitivity: model_minus_no_action_net sign across {len(sens)} cost settings = "
          f"{'always positive' if signs == {1} else signs}")
    print(f"report: {OUT_DIR}/profit_regret.json")
    print("Done. Unit counts measured; dollar figures simulated (assumption-conditioned).")


if __name__ == "__main__":
    main()

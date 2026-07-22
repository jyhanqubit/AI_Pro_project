# V2 Profit / Regret Ledger (V2-02)

이야기를 부풀리지 않고 forecast 품질을 금액으로 변환한다. Predictive lift 는 운영 profit 으로
변환되어 살아남아야만 유용하다.

> **Status: implemented + run (V2-02).** 회계 `optimization/ledger.py` (pure functions),
> runner `optimization/ledger_run.py` (`make v2-ledger`), typed contract `contracts/v2/ledger.py`.
> 첫 실행 (assumption set `v2-assumptions-1`, JC 2024, 114,079 zone-hour decisions): V2-01
> promoted forecast 가 seasonal-naive 현상 유지 대비 **+$103,271** 순이익 (부호는 9개 cost
> setting 전부에서 positive), regret vs Oracle **$218,697**. Unit counts 는 measured; dollars 는
> `simulated` (assumptions `sourced: false`). Scope: single-period stocking; 여기서는
> **relocation = 0** (origin→destination moves 는 V2-04). 전체 결과: `reports/v2/ledger/`.

## Accounting model

zone-hour decision 당 ledger 는 다음을 회계한다:

```text
contribution_margin   = realized_rentals * margin_per_rental        (revenue side)
shortage_cost         = unmet_demand     * shortage_externality     (cost side)
overflow_cost         = dock_overflow    * overflow_penalty
relocation_cost       = moved_units      * distance_cost
------------------------------------------------------------------
net = contribution_margin - shortage_cost - overflow_cost - relocation_cost
regret = net(Oracle) - net(policy)
```

## Integrity rules (non-negotiable)

1. contribution margin 을 shortage externality 와 **분리** — 둘은 하나의 숫자가 아니라 별개의
   ledger 다.
2. **이중 계산 금지**: stockout 으로 인한 lost margin 은 `shortage_cost`
   (externality) 또는 감소한 `contribution_margin` 으로 포착되며, 결코 둘 다는 아니다.
3. Costs 와 elasticity 는 `config/v2/` 의 **버전 관리된 assumption set** 에서 온다 (예:
   `config/v2/assumptions.yaml`), 각 수치는 `claim_status: assumption` 으로 라벨링.
4. **Oracle** = perfect-foresight offline 상한. regret 의 천장이며, 달성 가능한
   결과로 주장되지 않는다.
5. 모든 ledger 수치는 result envelope (`run_id`/`artifact_id`/`mode`/`claim_status`/
   `freshness`) 를 지닌다.

## Assumption set (versioned)

```yaml
# config/v2/assumptions.yaml  (template — fill with sourced values, label each)
version: v2-assumptions-0
margin_per_rental: null          # assumption; cite source
shortage_externality: null       # assumption
overflow_penalty: null           # assumption
distance_cost_per_unit_km: null  # assumption
elasticity: null                 # assumption (used by V2-05 pricing)
```

## Artifact schema — `reports/v2/ledger/profit_regret.json`

```jsonc
{
  "run_id": "run_...",
  "assumption_set_version": "v2-assumptions-0",
  "by_policy": {
    "no_action": { "net": null, "regret_vs_oracle": null },
    "greedy":    { "net": null, "regret_vs_oracle": null },
    "milp":      { "net": null, "regret_vs_oracle": null },
    "mpc":       { "net": null, "regret_vs_oracle": null },
    "oracle":    { "net": null, "regret_vs_oracle": 0 }
  },
  "components": { "contribution_margin": null, "shortage_cost": null,
                  "overflow_cost": null, "relocation_cost": null },
  "claim_status": "pending"
}
```

## Acceptance

- Margin 과 externality 분리; 이중 계산 없음 (두 ledger 가 결코 같은 event 를 공유하지 않음을
  단언하는 unit test 추가).
- Assumptions 는 inline 상수가 아니라 버전 관리된 set 에서 로드.
- Oracle 이 존재하며 상한으로 라벨링됨.
- `V2_MPC_DECISIONING.md` 의 모든 policy 에 대해 Oracle 대비 regret 계산.

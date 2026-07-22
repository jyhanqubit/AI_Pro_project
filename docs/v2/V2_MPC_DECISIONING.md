# V2 Multi-period MPC Decisioning (V2-04)

네 개의 **mandatory** rebalancing policy 를 multi-period horizon 에 걸쳐 ledger objective 상에서
비교한다. `../OPTIMIZATION.md` 를 확장한다.

> **Status: implemented + run (V2-04).** Simulator `optimization/mpc.py`, runner
> `optimization/mpc_run.py` (`make v2-mpc`). 검증된 per-period greedy/MILP solver 를 재사용하는
> Receding-horizon loop. 결과 (8 zones, 72h, seeded commute scenario, ledger objective — cost 가
> 낮을수록 좋음): No Action 1126.7 · Greedy 1154.7 · single-period MILP 1086.9 · **MPC 740.3** ·
> Oracle 718.7. **MPC 가 최선의 feasible policy** (regret vs Oracle 가 단 21.6 — 3% 이내),
> single-period MILP 대비 shortage+overflow 를 대략 절반으로 줄임; 여기서 Greedy 는 net-harmful
> (reposition 지출 > 완화된 imbalance). 전부 feasibility-checked (infeasible 0); Oracle 이 모두를
> bound (regret ≥ 0). Dollar figures 는 `simulated` (문서화된 scenario 상의 policy 비교). 7 tests.
> 전체 결과: `reports/v2/mpc/`.

## Mandatory policies

```text
No Action           : baseline, do nothing (lower bound)
Greedy              : feasible greedy fill toward forecast need
Single-period MILP  : constrained optimum for one period
MPC                 : receding-horizon control over the forecast horizon
```

Optional (완료 조건 아님): SP / CVaR (stochastic / risk-averse). RL 은 research-only.

## Objective & constraints

Objective = ledger net (`V2_PROFIT_REGRET_LEDGER.md`): expected shortage + overflow +
relocation cost 를 최소화 (동등하게 net 을 최대화). Constraints (전부 강제, infeasibility 명시):

```text
move ≤ available at origin
destination inventory ≤ capacity
non-negative integer moves
total movement ≤ vehicle/route capacity
```

## Protocol

- 모든 policy 는 **동일한 instances** 와 **동일한 forecast** (promoted model 유래) 상에서 실행.
- MPC 는 horizon 에 걸친 forecast 를 사용 — **결코 future truth 아님** (no leakage).
- 생성된 모든 plan 은 카운트되기 전에 feasibility-checked.
- policy 별 Oracle 대비 regret 을 보고.

## Artifact schema — `reports/v2/mpc/policy_comparison.json`

```jsonc
{
  "run_id": "run_...",
  "horizon": null,
  "instances": null,
  "policies": {
    "no_action": { "net": null, "regret_vs_oracle": null, "feasible": null },
    "greedy":    { "net": null, "regret_vs_oracle": null, "feasible": true },
    "milp":      { "net": null, "regret_vs_oracle": null, "feasible": null },
    "mpc":       { "net": null, "regret_vs_oracle": null, "feasible": null }
  },
  "oracle": { "net": null },
  "infeasible_instances": [],
  "claim_status": "pending"
}
```

## Acceptance

- 네 policy 를 동일 instances 에서 비교; MPC leak-free.
- 모든 plan feasibility-checked; infeasibility 는 숨기지 않고 보고.
- 결과는 ledger 및 regret-vs-Oracle 로 연결됨.

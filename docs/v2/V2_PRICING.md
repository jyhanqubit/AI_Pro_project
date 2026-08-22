# V2 Dynamic Pricing & Experiment Dry-run (V2-05)

hard guardrail 을 갖춘 bounded incentive/pricing policy, 그리고 **offline** experiment dry-run.
실사용자가 없으므로 pricing 결과는 `simulated` — 결코 causal business 결과가 아니다.

> **Status: implemented + run (V2-05).** Policy `ml/pricing/pricing_v2_eval.py`, runner
> `ml/pricing/pricing_v2_run.py` (`make v2-pricing`). Demand response 는 버전 관리된
> assumption-set elasticity 를 사용; objective 는 V2-02 ledger; bounds/safety 규칙은
> `config/pricing_v2.py` 에서. 결과 (576 seeded zone-hours): **guardrail 위반 0**, safety zones
> 는 base fare 유지, budget 준수 (0/40), **negative control** 이 심어둔 out-of-bounds surge 를
> audit 이 잡아냄을 확인. elasticity × surge-bound 에 대한 sensitivity grid, 그리고 effect ≈ 0 /
> CI 가 0 을 포함하는 **A/A switchback dry-run** (treatment effect 가 아니라 design 유효성).
> 전부 `simulated`. 7 tests. Artifacts: `reports/v2/pricing/{guardrail_audit,sensitivity}.json`.

## Policy

- Prices/incentives 는 bounded: `price ∈ [p_min, p_max]`, incentive `∈ [0, i_max]`.
- Elasticity 는 버전 관리된 assumption set (`config/v2/assumptions.yaml`,
  `claim_status: assumption`) 에서 온다. LLM 은 price 숫자를 직접 계산하지 않는다.
- Policy 는 guardrails 를 지키며 ledger objective 를 최적화한다.

## Guardrails (audited)

```text
G1  no price outside [p_min, p_max]
G2  no incentive outside [0, i_max]
G3  no action with negative expected margin
G4  bounded total incentive budget per period
G5  monotonicity sanity: higher shortage risk ⇒ non-decreasing incentive (within bounds)
```

Guardrail audit 는 추천된 모든 action 을 G1–G5 에 대해 검사하고 위반을 기록한다
(target: zero).

## Experiment dry-run

- fixtures 위에서 A/B 또는 switchback 을 **offline** 으로 설계; 결과는 `simulated` 로 라벨링.
- design 의 유효성 (예: A/A CI 가 0 포함) 을 보고 — 실제 rider 에 대한 treatment effect 가 아님.
- online learning / bandits 없음 (실제 사용자 로그가 필요 → base contract 로 금지).

## Artifact schemas

`reports/v2/pricing/sensitivity.json`:

```jsonc
{
  "run_id": "run_...",
  "assumption_set_version": "v2-assumptions-0",
  "price_grid": [],
  "expected_net_by_price": [],
  "elasticity_used": null,
  "claim_status": "simulated"
}
```

`reports/v2/pricing/guardrail_audit.json`:

```jsonc
{
  "run_id": "run_...",
  "checks": { "G1": null, "G2": null, "G3": null, "G4": null, "G5": null },
  "violations": [],
  "claim_status": "pending"
}
```

## Acceptance

- 모든 추천이 bounds 내; guardrail 위반 = 0.
- Elasticity 는 버전 관리된 assumptions 에서; pricing 결정은 LLM 이 내리지 않음.
- Experiment 는 `simulated` 로 라벨링; causal 주장 없음.

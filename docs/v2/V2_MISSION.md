# V2 Mission & Contract

_출처: `CLAUDE_V2_APPEND_REVISED.md` (`CLAUDE.md`에서 import됨). 이 문서는 사람이 읽을 수 있도록 풀어 쓴
버전이며, 둘이 어긋날 경우 addendum이 authoritative합니다._

## 1. Mission

V2는 기능 확장 릴리스가 아닙니다. **LLM net-business-value verification** 릴리스입니다.
V2가 증거로 답해야 하는 단 하나의 질문:

> LLM으로 추출한 event가 calendar/history 및 단순 rule baseline 대비 측정 가능한 predictive lift를
> 만들어내는가, 그리고 그 lift가 LLM 자체의 incremental cost를 차감한 후 운영 profit으로
> 전환되는가?

Value chain:

```text
Measured model productization
→ H3 multi-holdout
→ Rule vs LLM event ablation
→ Profit / Regret Ledger
→ MPC / bounded pricing
→ GraphRAG correctness benchmark
→ artifact-backed product UI
```

## 2. Domain (unchanged)

```text
ShockFlow AI · Citi Bike · New York City
grain: Station / H3 Zone / Borough
```

Seoul / Gwanak / ParcelFlow / parcel-logistics contract를 **도입하지 마십시오**. Domain은
Citi Bike / NYC로 유지됩니다. 이는 V2-00의 명시적 correction target입니다.

## 3. Source of truth (priority order)

```text
1. current command / test result
2. versioned artifact (reports/v2/**)
3. code and contract
4. current docs
5. old handoff
```

Stale number는 절대 그대로 복사하지 않습니다. 어떤 숫자는 현재 command, test, 또는 versioned artifact가
그것을 생성할 때만 인용 가능합니다. 이는 특히 v1 숫자에 적용됩니다(예: `../V2_HANDOFF_REPORT.md`의 WAPE
수치) — 이들은 v1을 기술하므로 어떤 V2 문서가 인용하기 전에 반드시 re-measure되어야 합니다.

## 4. Required evidence (the 7 gates)

| # | Evidence | Owning phase | Artifact |
|---|---|---|---|
| 1 | Promoted measured model is served (non-demo modes) | V2-01 | `reports/v2/holdout/` + served model manifest |
| 2 | H3 multi-holdout report exists | V2-01 | `reports/v2/holdout/h3_multiholdout.json` |
| 3 | No-Event / Rule-Event / LLM-Event separated | V2-03 | `reports/v2/llm_value/` |
| 4 | Predictive lift translated into profit/regret | V2-02 | `reports/v2/ledger/` |
| 5 | LLM incremental cost included | V2-03 | `reports/v2/llm_value/incremental_value.json` |
| 6 | GraphRAG correctness + relevance evaluated | V2-06 | `reports/v2/copilot/` |
| 7 | All UI metrics point to artifacts | V2-07 | UI results carry `run_id`/`artifact_id` |

## 5. Profit integrity

- **contribution margin**과 **shortage externality**를 분리하십시오. 절대 합치지 마십시오.
- lost margin을 shortage cost와 double-count하지 마십시오.
- Cost와 elasticity는 inline 상수가 아니라 **versioned assumption set**(`config/v2/`)에 둡니다.
- **Oracle** policy는 offline upper bound일 뿐입니다 — 절대 달성 가능한 결과로 제시하지 마십시오.

## 6. Mandatory policies

```text
No Action · Greedy · Single-period MILP · MPC     (required, must be compared)
SP / CVaR                                          (optional)
RL / QAOA                                          (research-only — NOT a completion condition)
```

## 7. LLM boundaries

- LLM은 **event structuring, tool routing, explanation**에만 사용됩니다.
- LLM은 demand, price, profit 숫자를 직접 계산하지 **않습니다**.
- 뒤에 typed tool result가 **없는** 숫자 Copilot 답변은 rejected됩니다.

## 8. Claims taxonomy

모든 API/UI 결과는 `run_id`, `artifact_id`, `mode`, `claim_status`, `freshness`를 담습니다.
허용되는 `claim_status` 값:

```text
measured · offline_benchmark · simulated · pending_live_label
assumption · blocked_data · blocked_external · demo_fixture · research
```

전체 envelope와 현재(모두 `pending`인) matrix는 `V2_CLAIMS_MATRIX.md`를 참조하십시오.

## 9. Invariants carried over from the base contract

Temporal correctness 및 `available_at <= forecast_cutoff` leakage 규칙; UTC 저장 +
`America/New_York` local aggregation; temporal forecasting에 random split 금지; mode 분리
(demo/replay/live/research); metric/news/citation 조작 금지; feature attribution으로부터 causal
claim 금지; quantum-advantage claim 금지; simulator ≠ hardware; documented migration이 phase의
일부가 아닌 한 v0/v1 contract는 backward-compatible로 유지.

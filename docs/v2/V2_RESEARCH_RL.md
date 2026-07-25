# Research Mode — Learned Rebalancing Policy (RL)

**Status:** Research 전용. RL은 V2 completion 조건이 **아닙니다**
(`CLAUDE_V2_APPEND_REVISED.md` → "RL and QAOA are research-only"). `optimization/quantum/` 옆에 research
영역으로 둡니다. **RL advantage는 주장하지 않습니다** — 프로젝트의 상시 규칙인 "no quantum advantage"와
동일한 태도입니다.

## 왜 만들었나

프로젝트에는 이미 엄정한 재배치 scoreboard(V2-04)가 있습니다. policy 다섯 개 —
No-Action / Greedy / single-period MILP / **MPC** / **Oracle** — 를 하나의 V2-02 ledger로 seeded commute
시나리오에서 채점하고, Oracle을 offline upper bound로 둬서 모든 policy의 `regret_vs_oracle ≥ 0`이 되게 합니다.
RL은 이 scoreboard에 *learned-control* baseline을 추가합니다. 그래서 손으로 설계한 policy들과 직접 비교되고,
별도의 맞춤 metric으로 재는 게 아닙니다.

## 두 learner, 하나의 scoreboard

둘 다 **numpy만** 씁니다(torch 없음). mandatory policy들과 같은 ledger + eval 시나리오로 채점합니다.
`make v2-rl`이 둘을 모두 돌리고 artifact 하나를 씁니다.

### 1. Tabular Q-learning (`optimization/rl/qlearning.py`)

target inventory를 **어떻게 shaping할지**를 global하게 학습하고, tested feasible move solver를 재사용합니다.

| 요소 | 정의 |
|---|---|
| **State** | `(hour_of_day ∈ 0..23, system_imbalance_bucket ∈ {−1,0,+1})` → 72개 state |
| **Action** | *global* target-shaping control `(alpha ∈ {0,0.5,1,1.5,2}, H ∈ {1,3,6})` → 15개 action |
| **Target 규칙** | `target = clip(capacity/2 − alpha · Σ forecast_net_over_H, 0, capacity)` |
| **Algorithm** | ε-greedy tabular Q-learning |

이 target 규칙이 built-in policy를 **포함**합니다: `alpha=0`은 No-Action, `alpha=1,H=1`은 single-period MILP
target, **`alpha=1,H=6`은 정확히 MPC**입니다. 즉 MPC가 자기 action 중 하나이고, 현실적인 최선은 MPC를
*재발견*하는 것입니다. state가 coarse하고 system-wide라 **zone별 정보가 전혀 없고**, 그게 점수를 제약합니다.

### 2. PPO (`optimization/rl/ppo.py`)

from-scratch numpy PPO (one-hidden-layer MLP policy + critic, diagonal Gaussian, GAE(λ), clipped
surrogate, entropy bonus, Adam — 전부 manual backprop). **zone별 continuous** env(`ContinuousRebalanceEnv`)
위에서 돌고, MPC가 실제로 쓰는 정보를 policy에 줍니다:

| 요소 | 정의 |
|---|---|
| **State** | zone별 `[inventory/cap, Σ forecast_H / cap]` + clock `[sin h, cos h]` → `2·z + 2` 차원 |
| **Action** | zone별 continuous **target fraction** `∈ [0,1]^z` → `target_j = round(frac_j · cap_j)` |
| **Algorithm** | PPO (policy gradient) — tabular의 state/action 병목 제거 |

### 공유하는 physics (둘 다)

두 env 모두 **tested per-period MILP solver**로 재배치하고, `optimization.mpc.simulate`와 같은
shortage/overflow 의미로 realized net flow를 적용합니다. reward는 시간당
`− (shortage_cost + overflow_cost + relocation_cost)` (V2-02 ledger).

`tests/unit/test_v2_rl.py`가 이 fidelity를 증명합니다: tabular env가 `(alpha=1,H=6)`에서
`simulate("mpc", …)`를 단위까지 재현하고 `(alpha=0)`이 No-Action을 재현합니다. continuous env는 상수 target
fraction에서 공유 move/realized helper와 일치하고, PPO는 reproducible하며 random policy를 이깁니다.

## Leakage 규율 (프로젝트 전체와 동일)

training은 **held-out demand seed**(`100..115`)를 쓰고, eval 시나리오(`seed=42`, `make v2-mpc`가 채점하는 바로
그 시나리오)는 training set에 **절대 넣지 않습니다**. agent가 eval noise를 보지 못하므로 보고된 regret은
암기된 값이 아닙니다. training은 simulated episode 위의 닫힌 **offline** loop입니다 — live user에 대한 online
학습도, bandit도 없습니다(둘 다 금지).

## 기대치

여기서 MPC는 이미 near-optimal(regret ≈ 21.6 vs Oracle)이고, Oracle까지 남은 gap은 **대부분 줄일 수 없는
forecast noise**입니다 (`realized = forecast + noise`; noise는 학습 불가이고, Oracle은 learner가 못 보는
realized demand를 봄). 그래서 상한은 **"MPC에 근접"이지 "MPC를 이김"이 아닙니다**. runner는 verdict를
수치에서 계산합니다 (`RL_APPROACHES_MPC` / `RL_UNDERPERFORMS_MPC` / `RL_MATCHES_OR_EXCEEDS_MPC_ON_THIS_SCENARIO`) —
단정하지 않고, 시나리오 하나에서 **일반적인 RL advantage를 주장하지 않습니다**.

PPO의 역할은 "tabular 점수를 제약한 건 알고리즘이 아니라 **representation**(coarse global state/action)이었다"는
진단을 검증하는 것입니다. PPO에 zone별 state/action을 주면 *tabular Q-learning을 앞서고 MPC 쪽으로* 이동해야
하고, artifact가 실제로 그렇게 기록합니다.

## 측정 결과 (`reports/v2/research/rl_rebalancing.json`)

seeded eval 시나리오(`seed=42`, 8 zone, 72h)에서 Oracle 대비 regret, 낮을수록 좋음:

| policy | regret | 비고 |
|---|---|---|
| oracle | 0.0 | offline upper bound (realized demand를 봄) |
| **mpc** | **21.6** | best; model-based receding-horizon |
| **rl_ppo** | 202.9 | zone별 continuous PPO |
| **rl_qlearning** | 247.8 | coarse global tabular |
| milp / no_action / greedy | 368 / 408 / 436 | |

`ppo_beats_tabular=true`, `best_rl=rl_ppo`, `beats_mpc=false`. 즉 더 풍부한 representation이 도움이 됐지만
(진단대로) MPC가 여전히 best입니다. (위 수치는 committed run에서 나온 것이고, 같은 seed면 재현됩니다.)

## 재현

```bash
make v2-rl        # python -m optimization.rl.run  (~5분: tabular 300 episode + PPO 60 iter)
```

Artifact: `reports/v2/research/rl_rebalancing.json` — `mode=research`, `claim_status=research`로 라벨됨.
`ResultEnvelope` validator(`contracts/v2/envelope.py`)가 research 값을 모든 product surface(demo/replay/live)
에서 **차단**하므로, 이건 operator/rider UI로 절대 새어 나가지 않습니다.

# 90초 데모 스크립트 — golden path

아래는 전부 **fixture 기반, 오프라인, API 키 불필요**로 동작합니다 (CLAUDE.md §3, §13, §17). 발표 모드는
Historical Replay입니다. 화면에 보이는 forecast는 라벨이 붙은 demo heuristic(`demo-heuristic-v1`)이고,
measured Phase 06 모델이 **아닙니다** — 둘은 의도적으로 구분해 둡니다.

## Setup (최초 1회)

```bash
make install
make api      # 터미널 1 — http://127.0.0.1:8000  (Demo Mode)
make web      # 터미널 2 — http://localhost:3000   (먼저 apps/web에서 `npm install` 필요)
```

Replay window는 2026-07-12 12:00 → 18:00 (America/New_York)입니다. 이 구간을 가로지르는 curated event가
둘 있습니다: **14:00**에 available해지는 **transit disruption**(Hoboken Terminal + City Hall), 그리고
**15:00**에 available해지는 **large venue event**(Newport)입니다.

## 진행 (~90초)

1. **Alert — Control Tower.** cutoff **13:59**에서 시작합니다. 아직 available한 event가 없어
   (`available_at ≤ cutoff`, §5.2) 모든 zone의 event-aware forecast가 baseline과 같고 delta는 `0.00`입니다.
   "quiet" 상태입니다.

2. **14:00 → 14:30으로 전진.** transit event가 available해집니다. 추출되어 graph에 들어가고, 그 as-of graph
   feature가 Hoboken/City Hall zone의 event-exposure를 올립니다. 해당 forecast가 baseline 위로 올라갑니다
   (양의 delta). 다시 **15:30**으로 전진하면 Newport venue event가 세 번째 이동 zone을 더합니다.

3. **Why — Why Changed.** 이동한 zone 하나를 엽니다. 화면이 전체 provenance chain
   `Article → Event → H3Zone → Feature`를 보여줍니다: source article의 evidence span, 추출된 event(type,
   effect direction, severity, confidence), 그것이 기여한 구체적 graph feature 값, 그리고 model-attributed
   forecast delta. 설명은 **절대** evidence-free가 아니며(§12, §13), "model-attributed"이지 "causal"이
   아닙니다(§4).

4. **Simulate — Scenario Lab.** transit event를 **off**로 토글합니다. 해당 zone의 counterfactual forecast가
   baseline으로 되돌아가고(delta → 0), delta가 그 event의 graph exposure에 대한 투명한 함수임을 증명합니다.
   다시 on으로 하면 surge가 복원됩니다.

5. **Act — Rebalancing Planner.** event가 live인 상태(cutoff 15:30)에서 event zone은 이제 **deficit**입니다
   (forecast surge가 target을 올렸기 때문). 계획을 풀면(MILP), surplus인 quiet-zone station(Grove St,
   Exchange Place)에서 세 event zone으로 자전거가 이동합니다. 계획은 각 origin → destination 이동, 수량,
   거리를 나열하고, 명시적 **feasibility** 검사를 통과하며, shortage 감소(데모 instance에서 8 → 0 units)를
   보고합니다. method를 **greedy**로 바꿔 비교해 보세요 — 둘 다 feasible.

6. **(선택) Research aside.** `make rebalance-demo`는 single edge에 대한 **Quantum Research Mode** QUBO도
   돌려 "QUBO brute-force energy == exact enumeration energy → match"를 출력합니다. 이건 research 전용 —
   simulator이지 하드웨어가 아니며 quantum-advantage 주장은 없습니다(§14.2).

## 한 줄 backing check

```bash
make rebalance-demo
```

greedy / MILP / exact-enumeration 일치와 QUBO 검증을 출력하므로, "Act" 단계를 UI 없이 재현할 수 있습니다.

## 이 데모에서 정직한 점

- **Fixture이지 live 아님.** 뉴스와 station 재고는 curated fixture이고, live collector는 opt-in이며 기본
  off입니다. fixture 데이터를 live로 보여주지 않습니다.
- **Demo heuristic이지 학습 모델 아님.** replay forecast는 `demo-heuristic-v1`입니다. measured leaderboard는
  `README.md` / `docs/EVALUATION_PROTOCOL.md`에 있습니다.
- **여기서 event lift는 measured metric이 아님.** June 평가 window에서는 curated event가 트립 데이터보다
  뒤라, measured forecast lift가 null입니다(`docs/KNOWN_LIMITATIONS.md`). 이 데모는 예측 이득의 증명이
  아니라, cutoff as-of로 *기계 장치*(extraction → graph → feature → delta → action)가 동작함을 보입니다.

## 이 골든패스 다음에 — V2 measured surface

이 스크립트는 v0 golden path(Alert → Why → Simulate → Act)입니다. **측정된** V2 결과(promoted model의 H3
multi-holdout, LLM value ablation, profit/regret ledger, MPC 정책 비교, pricing guardrail, Copilot
grounding)는 별도로 artifact가 뒷받침하며, `README.md`의 "V2 — LLM 순가치 검증" 절과
[docs/v2/](v2/)에서 확인할 수 있습니다. 한 번에 검증하려면:

```bash
make v2-final   # 3개 gate + reports/v2/final/claim_matrix.json → V2_COMPLETE
```

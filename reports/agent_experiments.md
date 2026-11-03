# Agent experiments — 실측 보고서

모든 숫자는 아래 명령을 실제로 실행해 나온 값이며, 각 결과 JSON 에 커밋 해시와 명령이 적혀 있습니다.
실행하지 못한 항목은 **미실행** 으로 표시합니다.

## 작업 1. MCP 토큰 측정과 결과 요약 비교

- 산출 스크립트: `python -m experiments.mcp_tokens` → `reports/agent_experiments/mcp_tokens.json`
- 조건: 커밋 `fb5d943` 기준 작업 트리(결과 JSON 의 `git_commit` 참고), 전송 `mcp_stdio`(실제
  `services.mcp.server` 를 stdio 로 띄워 호출), cutoff `2026-07-12T18:00:00-04:00`(데모 창 끝),
  mode `historical_replay`, seed 42(난수 사용 없음), 토크나이저 `tiktoken cl100k_base`(근사, 제공사 토크나이저와
  다를 수 있음), 직렬화 compact UTF-8 JSON, `freshness` 상수 치환.

### 1-1. 도구 정의 토큰 (5개 도구, `services/mcp/server.py`)

| 도구 | name+description+input_schema | +output_schema 포함 |
|---|---:|---:|
| get_graph_context | 102 | 806 |
| get_operator_statistics | 80 | 588 |
| get_metric | 128 | 663 |
| get_model_forecast | 76 | 587 |
| get_pricing_quotes | 477 | 1,342 |
| **합계** | **865** | **3,988** |

output_schema 를 함께 보내는 클라이언트라면 정의 토큰이 4.6배가 됩니다. `get_pricing_quotes` 는 `PricingRules`
중첩 스키마 때문에 입력 스키마만으로도 전체의 55% 를 차지합니다.

### 1-2. 시나리오별 원본 vs 요약 응답

| 시나리오 | 도구 (정의 토큰) | 원본 응답 | 요약 응답 | 감소율 | 답 보존 확인 |
|---|---|---:|---:|---:|---|
| A. 특정 zone 다음 1시간 예측 조회 | get_model_forecast (76) | 1,067 | 263 | 75.4% | zone 892a107216bffff 예측 8.3 양쪽 동일, serving_hour·algorithm·run_id·claim_status 보존 |
| B. 이벤트 근거 조회 (cutoff 기준) | get_graph_context (102) | 328 | 324 | 1.2% | 이벤트 2건의 id·type·근거 문장·최대 delta zone 동일, cutoff 보존 |
| C. 운영 상태(부족/급등, 재배치 입력) 조회 | get_operator_statistics (80) | 5,265 | 664 | 87.4% | 부족 정류장 17, 부족 147대, 이용률 0.48, 최대 급등 zone 892a10723b7ffff(delta 4.5) 동일 |
| D. (보조) 최적 재배치 정책 지표 | get_metric (128) | 74 | 74 | 0.0% | 이미 enveloped 숫자 하나라 요약 변형 없음 |

요약 방식(`experiments/mcp_summary.py`): provenance 블록 유지, 집계값 유지, 질문에 필요한 행만(A: 요청 zone,
B: 이벤트당 최대 delta zone 1개 + zone 수, C: 급등·부족 상위 3개 zone, 6개 필드), 원본은 `full_result_ref`
(tool, args, run_id, artifact_id) 로 참조. 요약 도구는 별도 서버 `experiments/mcp_summary_server.py`
(3개 도구, 정의 358 토큰)에 두었고 기존 5개 도구는 그대로입니다.

### 1-3. 도구를 단계별로만 노출했을 때 (정의 토큰)

| 시나리오 | 5개 전부 | 필요한 도구만 | 감소율 | 카탈로그(이름+첫 문장, 210) + 선택 도구 | 감소율 |
|---|---:|---:|---:|---:|---:|
| A | 865 | 78 | 91.0% | 288 | 66.7% |
| B | 865 | 104 | 88.0% | 314 | 63.7% |
| C | 865 | 82 | 90.5% | 292 | 66.2% |
| D | 865 | 130 | 85.0% | 340 | 60.7% |

(필요한 도구만 노출한 값이 1-1 의 개별 값보다 2 토큰 큰 것은 리스트 괄호 때문입니다.)

### 결론 (3줄)

1. 토큰은 도구 정의가 아니라 **응답** 에서 나간다. 큰 응답(운영 상태 5,265)은 집계 + 상위 N 행 + 참조로 87% 를
   줄이면서 질문의 답(부족 수, 이용률, 최대 급등 zone)을 그대로 보존했다.
2. 응답이 이미 작으면(이벤트 2건 328, 지표 74) 요약 블록의 고정 비용 때문에 이득이 없다(1.2%, 0%). 요약은
   행 수가 많은 도구에만 붙이는 것이 맞다.
3. 도구 정의는 필요한 도구만 노출하면 85~91%, 카탈로그 뒤 선택 방식이면 61~67% 줄고, output_schema 를
   함께 보내는 클라이언트에서는 절대량이 4.6배라 단계별 노출의 효과가 더 커진다.

## 작업 2. SHAP 설명 모듈 — 미실행 (작업 1 확인 후 진행)

## 작업 3. 재학습 판단 — 미실행 (작업 1 확인 후 진행)

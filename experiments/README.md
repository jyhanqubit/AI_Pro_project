# experiments/ — 면접용 실측 실험

저장소의 서빙 코드, 승격 모델, 커밋된 지표는 건드리지 않고 **같은 아티팩트와 fixture 를 읽어** 숫자를 새로 재는
모듈들입니다. 결과는 `reports/agent_experiments/*.json` 에 쓰고, 표와 결론은 `reports/agent_experiments.md` 에
정리합니다. 모든 결과 파일은 커밋 해시(`git_commit`)와 실행 명령(`command`)을 담습니다.

## 설치

```bash
make install                          # 기본 하네스 (잠금 파일 기준)
pip install -e ".[experiments]"       # tiktoken, shap (잠금 파일에는 없음, 선택 설치)
```

## 실험 1: MCP 토큰 측정 (`experiments/mcp_tokens.py`)

```bash
make exp-mcp-tokens                   # = python -m experiments.mcp_tokens
python -m experiments.mcp_tokens --in-process   # stdio 대신 in-process 전송으로 (payload 동일)
```

- 측정 대상: `services/mcp/server.py` 가 노출하는 5개 도구 정의(name, description, input_schema;
  output_schema 포함 변형도 별도 집계), 시나리오별 원본 응답(실제 stdio 서버 호출)과 요약 응답,
  단계별 노출(필요 도구만 / 카탈로그 + 선택 도구) 토큰.
- 토크나이저: `tiktoken` `cl100k_base` **근사**. 직렬화는 compact UTF-8 JSON, `freshness` 는 상수로 치환.
- 요약 도구는 기존 서버를 바꾸지 않고 `experiments/mcp_summary_server.py` 에 별도 서버(3개 도구)로
  둡니다: `python -m experiments.mcp_summary_server`.
- 샌드박스에서는 `openaipublic.blob.core.windows.net` 접근이 막혀 있어 `js-tiktoken@1.0.15` npm 패키지의
  rank 파일을 `.tiktoken` 형식으로 복원해 `TIKTOKEN_CACHE_DIR` 에 넣고 썼습니다. 복원 파일의 sha256 은
  tiktoken 이 기대하는 `223921b7…b2a7` 과 일치합니다. 인터넷이 되는 환경에서는 그냥 실행하면 됩니다.
- 테스트: `tests/integration/test_experiments_mcp_tokens.py` (요약이 답을 보존하는지, 토큰 수 재현성,
  단계별 노출이 전체보다 비싸지지 않는지). 인코딩 파일이 없으면 토큰 테스트만 사유와 함께 skip.

## 데이터 준비 (실험 2, 3 공통)

```bash
make download-citibike JC=1 MONTHS="202601 202602 202603 202604 202605 202606 202607 202608 202609"
```

저지시티 월별 아카이브(각 1~4 MB)를 `data/raw/citibike/` 에 받습니다. `experiments/_panel.py` 가 저장소 파이프라인으로
패널을 만들고 `data/processed/experiments/panel_<hash>.pkl` 에 캐시합니다(첫 실행 약 2.5분, 이후 즉시).

## 실험 2: SHAP 설명 (`experiments/shap_explain.py`)

```bash
make exp-shap                         # = python -m experiments.shap_explain --months 2026-08 2026-09 --n 3000 --seed 42
```

승격 모델(`reports/v2/holdout/promoted_model.joblib`)에 `shap.TreeExplainer` 를 붙여 글로벌 평균 |SHAP| 상위 10,
대표 예측 3건의 상위 5 기여, 트리 gain / permutation importance 와의 순위 비교, 상위 피처의 누수 판정
(`pipelines/features/lags.py` 규칙 대조)을 `reports/agent_experiments/shap_explain.json` 에 씁니다.
테스트: `tests/unit/test_experiments_drift_explain.py`(누수 매핑), `tests/integration/test_experiments_model_explain.py`
(gain importance 결정성, SHAP 재현성과 합 = 예측; shap 없으면 skip).

## 실험 3: 재학습 판단 (`experiments/retrain_gate.py`)

```bash
make exp-retrain-gate                 # = python -m experiments.retrain_gate (기준 2026-01..05, drop 5%, seed 42)
```

기준 월 피처 분포 대비 월별 PSI(10분위 구간), 챔피언 월별 WAPE, 규칙 판정(keep / retrain / review), 판정이 나온
out-of-sample 월마다 챌린저(같은 레시피, 평가 월 이전 전체로 재학습) 비교를 `reports/agent_experiments/retrain_gate.json`
에 씁니다. 테스트: `tests/unit/test_experiments_drift_explain.py` (PSI 0/단조/재현성, NaN 구간, 판정 임계값).

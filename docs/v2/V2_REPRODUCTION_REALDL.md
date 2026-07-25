# 실데이터 재현 — S3에서 NYC trip 내려받아 borough ablation 재실행

**목적:** V2-03의 결론(구조화 event feed는 예측 개선 +2.69%, LLM-from-news는 개선 없음)을 **새로 내려받은
실데이터**로 재현. 기존 `data/raw/nyc`가 이 컨테이너에 없어 `blocked_data`였던 부분을 직접 실행.

## 다운로드

- source: 공개 S3 버킷 `s3.amazonaws.com/tripdata` (키 불필요, `make download-citibike`).
- 받은 것: **2026-01 … 2026-05 (5개월)**, 합계 약 **14.5M trips** (git-ignored, 커밋 안 함).

## 재실행 결과 (2건, 모두 provider=mock — 이 컨테이너에 LLM 키 없음)

재현 artifact: `reports/v2/llm_value/reproductions/borough_realdl_mock_*.json`.

| window (train/test) | n_train | A0 → A1 (WAPE) | A1−A0 structured lift | A2−A1 news |
|---|---|---|---|---|
| **Jan–Apr / May** (committed와 동일) | 10,655 | 0.0908 → **0.0883** | **measured_improvement +2.69%**, CI [1.08, 6.71] | negative_lift, net **−$18,195** |
| Feb–Apr / May (train 3개월) | 7,780 | 0.0885 → 0.0877 | **inconclusive** (CI [−1.12, 4.05]) | (mock) |
| _(참고) committed 원본_ | 10,655 | 0.0908 → 0.0883 | +2.69%, CI [1.08, 6.71] | negative_lift, net −$17,789 (real Claude) |

## 결론

1. **구조화 event feed lift는 재현됨 (measured).** train window를 committed와 맞추면(Jan–Apr, n_train
   10,655) A0=0.0908 → A1=0.0883, **+2.69%, CI [1.08, 6.71]** 로 **committed와 동일**하게 나옵니다. permit
   feed는 LLM에 의존하지 않으므로 provider와 무관하며, 실제로 다운로드한 원천 데이터에서 그대로 재현됩니다.
2. **news-null 결론은 provider에 robust.** LLM 키 없이 **mock 추출**만으로도 news arm은 net **−$18,195**
   (negative_lift, LFV MEANINGFUL_NEGATIVE −3.0%) — committed real-Claude 결과(−$17,789)와 방향·크기 모두
   유사. 즉 "뉴스는 예측을 못 돕는다"는 결론은 추출기 품질 문제가 아닙니다.
3. **구조 lift는 train 데이터 양에 민감(한계).** train을 3개월(7,780행)로 줄이면 A1−A0가
   **inconclusive**(CI∋0)로 바뀝니다. +2.69%는 실재하지만 충분한 학습 구간을 필요로 하며, 좁은 window에서는
   유의성이 사라집니다 — CTO 보고 시 "robust한 대박"이 아니라 "조건부 measured lift"로 표현해야 정확합니다.

## 무결성 노트

- committed `incremental_value_borough.json`(real-Claude, −$17,789)은 **그대로 유지**했고, 재실행 산출물은
  `reports/v2/llm_value/reproductions/`에 별도 보관(문서·claim matrix가 인용하는 원본을 덮어쓰지 않음).
- 재현은 `mode=historical_replay`, 금액은 `simulated`(assumption-conditioned). trip 단위는 measured.

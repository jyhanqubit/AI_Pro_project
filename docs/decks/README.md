# Decks — 프레젠테이션 산출물

프로젝트(v1+v2)를 요약한 발표용 장표. 모든 수치는 `reports/v2/**` committed artifact에서 나온 값이며,
설명은 한국어 / 기술용어는 영어로 통일했습니다.

| 파일 | 내용 |
|---|---|
| `ShockFlow_AI_overview.pptx` / `.html` | 2페이지 요약 — 1p 거시(워크플로우·배경·사업·차별성), 2p 미시(단계별 기술·지표) |
| `ShockFlow_AI_CTO_review.pptx` | CTO 보고용 12슬라이드 — 기능 요소·사용 데이터·데이터 예시/해석·모델과 선택 이유·예측 판별과 정답지·LLM value 판정·의사결정·고도화 로드맵 |

## 재생성 (16:9)

```bash
cd docs/decks && npm install pptxgenjs   # 최초 1회
node gen_overview_deck.js                # → ShockFlow_AI_overview.pptx
node gen_cto_review.js                   # → ShockFlow_AI_CTO_review.pptx (경로는 스크립트 상단 참고)
```

생성 스크립트는 pptxgenjs(LAYOUT 13.33×7.5")로 네이티브 도형/텍스트를 그립니다(이미지 캡처 아님).

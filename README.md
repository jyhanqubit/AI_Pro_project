# ShockFlow AI

이벤트를 인지하는 도시 모빌리티 수요 예측 및 차량 재배치 의사결정 지원 시스템.

ShockFlow AI는 시간 정보가 붙은 이벤트에서 불규칙한 수요 충격을 감지해 추적 가능한 graph feature로 바꿉니다.
이 feature가 예측에 준 **모델 기여**(model-attributed) 영향(입증된 인과는 아닙니다)을 정량화한 뒤, 그 결과를
실제 운영에 쓸 수 있는 재배치 조치로 이어줍니다.

```text
Citi Bike 수요 이력
+ 시간 정보가 붙은 뉴스 / 이벤트 입력
+ 현재 station 재고
→ LLM 이벤트 추출 → Neo4j 이벤트 graph → as-of numeric graph feature
→ H3 Zone-시간 수요 예측 → 설명 및 시나리오 비교 → 실행 가능한 재배치 계획
```

개발 전반의 운영 계약은 [CLAUDE.md](CLAUDE.md)에 정리해 두었습니다.

## 운영 모드

모든 레코드와 응답, 화면은 자신의 모드를 명시합니다. `demo_fixture`, `historical_replay`,
`live`, `research` 중 하나입니다. **Demo Mode는 외부 API 키 없이 완전히 오프라인으로 돌아갑니다.**

## 시작하기

```bash
make install       # .venv 생성 + 패키지(editable)와 dev 도구 설치
make lint          # ruff check + format check
make typecheck     # mypy
make test          # pytest
make collect-demo    # 세 개의 fixture collector를 오프라인으로 돌리고 요약 출력
make build-features  # 수요 집계(H3 Zone x 로컬 시간) + 누수 방지 feature
make extract-events-demo  # 뉴스 fixture에서 이벤트 추출 (결정적 mock LLM)
make graph-upsert-demo    # 추출한 이벤트를 오프라인 event graph에 업서트 (idempotent)
make graph-features-demo  # 여러 cutoff에서 as-of graph feature 생성 (누수 방지)
```

> 윈도우에서 `make`를 쓸 수 없다면 위 명령에 대응하는 명령을 직접 실행하세요. 예를 들면
> `python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"` 처럼요.

실행 전에 `.env.example`을 `.env`로 복사하세요. 기본값은 안전하고 오프라인에서도 문제없이 동작합니다.

## 저장소 구조

| 경로 | 용도 |
|------|------|
| `contracts/` | 경계 전반에서 공유하는 타입 지정 Pydantic v2 data contract (§6) |
| `services/api/` | FastAPI 서비스 (Phase 07) |
| `pipelines/collectors/` | 데이터 collector: Citi Bike, 뉴스 fixture, GBFS |
| `pipelines/events/` | LLM 이벤트 추출 |
| `pipelines/features/` | 수요 집계(H3 Zone x 로컬 시간) + 누수 방지 feature |
| `ml/forecasting/` | baseline 및 이벤트 인지 예측 모델 |
| `optimization/classical/` | Greedy / MILP 재배치 |
| `optimization/quantum/` | QUBO / QAOA 리서치 모드 |
| `apps/web/` | Next.js 운영자 UI (Phase 07) |
| `config/` | 타입 지정 런타임 설정 |
| `data/fixtures/` | 큐레이션한 버전 관리 데모 fixture |
| `data/raw/`, `data/processed/` | 로컬 입력 / 산출물 (git 무시) |
| `docs/` | PRD, 아키텍처, contract, 평가, 상태 |
| `tests/` | `unit/`, `integration/`, `e2e/` |

## 상태

현재 진행 중인 단계와 검증된 명령, 남은 걸림돌은 [docs/STATUS.md](docs/STATUS.md)에서 확인하세요.

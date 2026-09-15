# V2-02 Predictive Lift — Coverage Report

- verdict: **blocked_data** (claim_enabled=False)
- coverage_ok: False
- unique_events: 2 (gate ≥ 20)
- affected_zone_hours: 15 (gate ≥ 200)
- unique_sources: 2 (gate ≥ 5)
- event_types: 2 (gate ≥ 3)

데모 fixture는 커버리지 게이트(이벤트/소스/타입/영향 zone-hour)에 크게 못 미쳐 predictive lift 주장은 blocked_data로 비활성입니다. 측정된 lift는 실제 겹치는 뉴스 backfill + 학습이 통과해야 가능하며(V2-01/V2-02), 이 오프라인 환경에서는 차단됩니다. 프로토콜(시계열 분할·purge/embargo·이벤트 블록 부트스트랩 CI·판정 규칙)은 tests/unit/test_predictive_lift.py에서 합성 데이터로 검증됩니다.
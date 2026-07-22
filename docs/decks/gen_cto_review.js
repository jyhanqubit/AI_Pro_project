const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.defineLayout({ name: "W", width: 13.333, height: 7.5 });
p.layout = "W";

const C = {
  ground: "0C1220", panel: "141E30", panel2: "1B2740", line: "2A3A54",
  txHi: "EEF3FB", tx: "AEBCD4", txLo: "7E8DA8",
  amber: "F5A02B", amberDim: "3A2A10", teal: "3AC6D4", tealDim: "0E2A33",
  good: "43C08A", crit: "F0656A", violet: "9C8BF0", blue: "5B8DEF",
};
const SANS = "Calibri", MONO = "Courier New";
const M = 0.5, CW = 12.333;

function S(label) {
  const s = p.addSlide(); s.background = { color: C.ground };
  s.addText(label, { x: 10.0, y: 0.3, w: 3.0, h: 0.28, fontFace: MONO, fontSize: 9.5,
    color: C.txLo, align: "right", margin: 0, valign: "middle", charSpacing: 1 });
  return s;
}
function head(s, ko, en, accent) {
  s.addShape(p.ShapeType.ellipse, { x: M, y: 0.45, w: 0.1, h: 0.1, fill: { color: accent || C.amber } });
  s.addText(en, { x: M + 0.18, y: 0.37, w: 10, h: 0.28, fontFace: MONO, fontSize: 10,
    color: C.txLo, charSpacing: 2, align: "left", margin: 0, valign: "middle" });
  s.addText(ko, { x: M, y: 0.64, w: 11.5, h: 0.6, fontFace: SANS, fontSize: 25, bold: true,
    color: C.txHi, align: "left", margin: 0 });
}
function sec(s, x, y, w, ko, en, color) {
  s.addText([{ text: ko, options: { color: color || C.amber, bold: true } },
             { text: en ? "  " + en : "", options: { color: C.txLo, bold: false } }],
    { x, y, w, h: 0.28, fontFace: MONO, fontSize: 11, charSpacing: 1, align: "left", margin: 0, valign: "middle" });
}
function card(s, x, y, w, h, accent) {
  s.addShape(p.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.07,
    fill: { color: C.panel }, line: { color: accent ? accent : C.line, width: 1 } });
}
function bul(items, numColor) {
  const runs = [];
  items.forEach((it, i) => {
    const pair = Array.isArray(it) ? it : [{ t: it }];
    runs.push({ text: "•  ", options: { color: numColor, bold: true, fontFace: SANS, fontSize: 11 } });
    pair.forEach((seg, j) => runs.push({ text: seg.t,
      options: { color: seg.c || C.tx, bold: !!seg.b, breakLine: j === pair.length - 1 } }));
    runs.push({ text: "", options: { breakLine: true, fontSize: 5 } });
  });
  return runs;
}
function kpiRow(s, y, tiles) {
  const n = tiles.length, gap = 0.12, w = (CW - gap * (n - 1)) / n;
  tiles.forEach((t, i) => {
    const x = M + i * (w + gap);
    card(s, x, y, w, 0.92);
    s.addText(t[0], { x: x + 0.14, y: y + 0.08, w: w - 0.28, h: 0.42, fontFace: MONO, fontSize: 20,
      bold: true, color: t[2] || C.amber, align: "left", margin: 0, valign: "middle" });
    s.addText(t[1], { x: x + 0.15, y: y + 0.5, w: w - 0.3, h: 0.36, fontFace: SANS, fontSize: 8.5,
      color: C.txLo, align: "left", margin: 0, valign: "top", lineSpacingMultiple: 0.95 });
  });
}
// generic table: cols=[{w,label}], rows=[[cell,...]] where cell=string|runArray
function table(s, x, y, cols, rows, opt) {
  opt = opt || {};
  const fs = opt.fs || 9.5, rowH = opt.rowH || 0.42, headColor = opt.head || C.amber;
  const tw = cols.reduce((a, c) => a + c.w, 0);
  let cx = x;
  cols.forEach(c => { s.addText(c.label, { x: cx + 0.08, y, w: c.w - 0.1, h: 0.28, fontFace: MONO,
    fontSize: 9, color: C.txLo, charSpacing: 1, align: "left", margin: 0, valign: "middle" }); cx += c.w; });
  s.addShape(p.ShapeType.line, { x, y: y + 0.3, w: tw, h: 0, line: { color: headColor, width: 1 } });
  const y0 = y + 0.36;
  rows.forEach((r, ri) => {
    const ry = y0 + ri * rowH;
    if (ri % 2 === 1) s.addShape(p.ShapeType.rect, { x, y: ry - 0.02, w: tw, h: rowH,
      fill: { color: C.panel }, line: { color: C.panel, width: 0 } });
    let rx = x;
    r.forEach((cell, ci) => {
      const common = { x: rx + 0.08, y: ry, w: cols[ci].w - 0.14, h: rowH, align: "left", margin: 0,
        valign: "middle", lineSpacingMultiple: 0.92, fontSize: fs };
      if (Array.isArray(cell)) s.addText(cell.map(seg => ({ text: seg.t,
        options: { color: seg.c || C.tx, bold: !!seg.b, fontFace: seg.m ? MONO : SANS } })), common);
      else s.addText(cell, { ...common, fontFace: SANS, color: C.tx });
      rx += cols[ci].w;
    });
  });
  return y0 + rows.length * rowH;
}
function codebox(s, x, y, w, h, title, lines, accent) {
  card(s, x, y, w, h, accent);
  s.addText(title, { x: x + 0.14, y: y + 0.08, w: w - 0.28, h: 0.24, fontFace: MONO, fontSize: 8.5,
    color: accent || C.teal, align: "left", margin: 0, valign: "middle", charSpacing: 1 });
  s.addText(lines.map((l, i) => ({ text: l,
    options: { color: i === 0 ? C.txHi : C.tx, breakLine: true, fontFace: MONO, fontSize: 8.2 } })),
    { x: x + 0.14, y: y + 0.34, w: w - 0.26, h: h - 0.42, align: "left", margin: 0, valign: "top", lineSpacingMultiple: 1.02 });
}
function foot(s, txt, badge, badgeColor) {
  s.addText(txt, { x: M, y: 7.16, w: 8.5, h: 0.24, fontFace: MONO, fontSize: 8, color: C.txLo, align: "left", margin: 0 });
  if (badge) s.addText(badge, { x: 6.5, y: 7.16, w: 6.33, h: 0.24, fontFace: MONO, fontSize: 8, color: badgeColor || C.good, align: "right", margin: 0 });
}

/* ============ 1 · COVER ============ */
(() => {
  const s = S("01 / 12");
  s.addShape(p.ShapeType.ellipse, { x: M, y: 1.7, w: 0.12, h: 0.12, fill: { color: C.amber } });
  s.addText("CTO 보고 · TECHNICAL REVIEW · 2026-07-22", { x: M + 0.2, y: 1.62, w: 11, h: 0.3,
    fontFace: MONO, fontSize: 11, color: C.txLo, charSpacing: 2, align: "left", margin: 0, valign: "middle" });
  s.addText([{ text: "ShockFlow ", options: { color: C.txHi } }, { text: "AI", options: { color: C.amber } }],
    { x: M - 0.03, y: 2.0, w: 12, h: 1.0, fontFace: SANS, fontSize: 54, bold: true, align: "left", margin: 0 });
  s.addText("Event-aware 도시 모빌리티 수요 예측 & 차량 rebalancing 의사결정 지원 — Citi Bike / New York City",
    { x: M, y: 3.05, w: 11.5, h: 0.4, fontFace: SANS, fontSize: 15, color: C.tx, align: "left", margin: 0 });
  s.addText("v1 (측정 모델·추천·실험·이상탐지) + v2 (LLM net-business-value 검증, V2-00…V2-09) 전체 리뷰",
    { x: M, y: 3.45, w: 11.5, h: 0.35, fontFace: SANS, fontSize: 12, color: C.txLo, align: "left", margin: 0 });
  kpiRow(s, 4.4, [
    ["0.4828", "H3 holdout WAPE (MASE 0.7996)", C.amber],
    ["+$103k", "예측 lift → profit (simulated)", C.good],
    ["21.6", "MPC regret vs Oracle", C.amber],
    ["0", "Copilot hallucination", C.teal],
    ["V2_COMPLETE", "31 artifacts · 3 gates", C.good],
  ]);
  s.addText("보고 범위: 기능 요소 · 사용 데이터 · 모델과 선택 이유 · 데이터 예시/해석 · 예측 판별과 정답지 · 고도화 로드맵",
    { x: M, y: 5.7, w: 12, h: 0.4, fontFace: SANS, fontSize: 11, color: C.tx, align: "left", margin: 0 });
  foot(s, "ShockFlow AI — CTO Technical Review", "모든 수치 = committed artifact 재현");
})();

/* ============ 2 · EXECUTIVE SUMMARY ============ */
(() => {
  const s = S("02 / 12");
  head(s, "Executive Summary — 한 장 요약", "WHAT WE BUILT · WHAT IS PROVEN");
  kpiRow(s, 1.5, [
    ["measured", "forecaster가 seasonal-naive를 이김", C.good],
    ["+2.69%", "structured event feed lift (measured)", C.good],
    ["−$17,789", "LLM-from-news 순가치 (null/negative)", C.crit],
    ["+10.43%", "synthetic ceiling (simulated, 조건 충족)", C.teal],
    ["research", "RL·Quantum — 완성 조건 아님", C.violet],
  ]);
  sec(s, M, 2.7, 6, "핵심 결론", "KEY TAKEAWAYS");
  s.addText(bul([
    [{ t: "측정된 승리: ", b: true, c: C.txHi }, { t: "promoted 모델이 naive 대비 개선, structured event feed는 +2.69% measured lift." }],
    [{ t: "정직한 null: ", b: true, c: C.txHi }, { t: "LLM-from-news feature는 예측을 개선하지 못함 — 원인까지 규명(source 조건 미충족)." }],
    [{ t: "가치는 조건부: ", b: true, c: C.txHi }, { t: "synthetic ceiling이 방법의 유효성을 입증 → 한계는 데이터 source." }],
    [{ t: "의사결정: ", b: true, c: C.txHi }, { t: "MPC가 best feasible policy, pricing guardrail 위반 0, Copilot hallucination 0." }],
  ], C.amber), { x: M, y: 3.05, w: 6.1, h: 3.6, fontFace: SANS, fontSize: 12, align: "left", margin: 0, valign: "top" });

  sec(s, 6.95, 2.7, 6, "CTO 관점 함의", "SO WHAT");
  s.addText(bul([
    [{ t: "LLM 투자 = 예측 정확도로 회수되지 않음", c: C.txHi, b: true }],
    [{ t: "LLM의 실측 가치는 event structuring·routing·grounded explanation(Copilot)에 있음.", }],
    [{ t: "예측 이득의 실체는 structured feed(허가·이벤트) — 뉴스가 아니라 구조화된 signal.", }],
    [{ t: "다음 투자처: event geocoding → H3-grain 검증, forward-looking dense source 확대.", }],
    [{ t: "모든 숫자는 artifact로 추적 — 과장·조작 없음(claim_status 강제).", }],
  ], C.teal), { x: 6.95, y: 3.05, w: 5.85, h: 3.6, fontFace: SANS, fontSize: 12, align: "left", margin: 0, valign: "top" });
  foot(s, "요약은 reports/v2/final/claim_matrix.json 기준", "measured / simulated / research 구분");
})();

/* ============ 3 · 기능별 요소 ============ */
(() => {
  const s = S("03 / 12");
  head(s, "기능별 요소 — 시스템 구성", "FUNCTIONAL COMPONENTS");
  const items = [
    ["01 Data Collection", "Citi Bike trip · news · GBFS 재고 · 허가 이벤트 수집, typed contract·배제 사유 기록", C.teal],
    ["02 LLM Event Extraction", "article → event(type·location·time·effect·severity·evidence), Pydantic 검증", C.teal],
    ["03 Neo4j Event Graph", "Article/Event/Zone/Station node, idempotent upsert, provenance 보존", C.teal],
    ["04 As-of Feature Store", "half-life·distance decay·spillover → numeric feature, leakage-gated", C.amber],
    ["05 Forecasting", "H3 zone×hour 수요 예측(HistGB), ablation·LFV metric", C.amber],
    ["06 Explanation · Copilot", "Article→Event→Zone→Feature→delta trace, GraphRAG typed-tool 질의", C.amber],
    ["07 Rebalancing · Pricing", "Greedy/MILP/MPC/Oracle + profit/regret ledger, bounded pricing", C.good],
    ["08 Monitoring · Labels", "run manifest·freshness, delayed-label loop(leakage-safe)", C.good],
  ];
  const cols = 4, rows = 2, gap = 0.18, cw = (CW - gap * (cols - 1)) / cols, ch = 2.15, y0 = 1.55;
  items.forEach((it, i) => {
    const x = M + (i % cols) * (cw + gap), y = y0 + Math.floor(i / cols) * (ch + 0.35);
    card(s, x, y, cw, ch, it[2]);
    s.addText(it[0], { x: x + 0.16, y: y + 0.16, w: cw - 0.3, h: 0.7, fontFace: SANS, fontSize: 13,
      bold: true, color: C.txHi, align: "left", margin: 0, valign: "top", lineSpacingMultiple: 0.95 });
    s.addText(it[1], { x: x + 0.16, y: y + 0.82, w: cw - 0.3, h: ch - 0.95, fontFace: SANS, fontSize: 9.5,
      color: C.tx, align: "left", margin: 0, valign: "top", lineSpacingMultiple: 1.02 });
  });
  s.addText("흐름: 01→02→03→04→05→(06 설명)→07 실행 · 08은 전 구간 상시 모니터링",
    { x: M, y: 6.75, w: 12, h: 0.3, fontFace: MONO, fontSize: 9.5, color: C.txLo, align: "left", margin: 0 });
  foot(s, "각 요소는 mode(demo/replay/live/research)를 명시", "");
})();

/* ============ 4 · 사용 데이터 ============ */
(() => {
  const s = S("04 / 12");
  head(s, "사용 데이터 — source · 규모 · 역할", "DATA SOURCES");
  const cols = [{ w: 2.7, label: "source" }, { w: 2.0, label: "grain" }, { w: 2.4, label: "규모(측정)" },
    { w: 3.4, label: "역할" }, { w: 1.83, label: "mode" }];
  table(s, M, 1.55, cols, [
    [[{ t: "Citi Bike Trip History", b: true, c: C.txHi }], "trip event", [{ t: "JC 30,947 rows·139 zone / NYC ~19.9M", m: true }], "수요 label의 원천(집계 전)", "historical"],
    [[{ t: "News fixture (JSONL)", b: true, c: C.txHi }], "article", [{ t: "23 clean NYC events", m: true }], "LLM event 추출 입력(replay)", "demo/replay"],
    [[{ t: "GBFS station_status", b: true, c: C.txHi }], "station·시각", [{ t: "실시간 재고 snapshot", m: true }], "현재 재고·rebalancing 입력", "demo/live"],
    [[{ t: "NYC Permitted Events", b: true, c: C.txHi }], "borough·기간", [{ t: "63,070 events (dense)", m: true }], "structured event feed(A1)", "historical"],
    [[{ t: "Weather (optional)", b: true, c: C.txLo }], "시각", [{ t: "MVP 제외", m: true, c: C.txLo }], "확장용(critical path 아님)", "—"],
  ], { rowH: 0.66, fs: 10 });
  card(s, M, 5.35, CW, 1.35, C.amber);
  s.addText([{ text: "해석  ", options: { color: C.amber, bold: true, fontFace: MONO, fontSize: 10 } },
    { text: "예측 label은 trip을 H3 zone×local hour로 집계해 만든 departures/arrivals/net_flow입니다. 재고(GBFS) 차이는 수요 label로 쓰지 않습니다(금지). ",
      options: { color: C.tx, breakLine: true } },
    { text: "'대용량'은 permit feed(63,070) — news(≈23)와 density가 근본적으로 다르며, 이 격차가 뒤(LLM value)의 핵심 원인입니다. 큰 trip 데이터(3GB)는 git 미포함, 측정 결과만 커밋.",
      options: { color: C.tx } }],
    { x: M + 0.15, y: 5.48, w: CW - 0.3, h: 1.1, fontFace: SANS, fontSize: 10.5, align: "left", margin: 0, valign: "top", lineSpacingMultiple: 1.05 });
  foot(s, "Demo Mode는 API 키 없이 오프라인 동작 · 라이브 collector는 기본 off", "");
})();

/* ============ 5 · 데이터 예시 ============ */
(() => {
  const s = S("05 / 12");
  head(s, "데이터 예시 — 실제 fixture 레코드", "DATA EXAMPLES (fixtures)");
  codebox(s, M, 1.55, 4.0, 2.5, "① TRIP (citibike_sample.csv)", [
    "started_at : 2026-07-12 13:05",
    "ended_at   : 2026-07-12 13:17",
    "start : HB101 Grove St PATH",
    "end   : HB102 Hoboken Term.",
    "lat/lng: 40.7196,-74.0431",
    "member_casual : member",
    "→ 집계 시 13시 departures+1",
  ], C.teal);
  codebox(s, 4.67, 1.55, 4.0, 2.5, "② NEWS → EVENT 추출", [
    "article a1  demo_wire",
    "\"PATH ... Grove St ...\"",
    "published: 2026-07-12T13:30-04",
    "─ LLM 추출 ─",
    "type: TRANSIT_DISRUPTION",
    "effect_dir: + / severity: prior",
    "evidence: [\"Grove St ...\"] (필수)",
  ], C.amber);
  codebox(s, 8.34, 1.55, 4.0, 2.5, "③ PERMITTED EVENT (NYC)", [
    "event_id: 888282",
    "name: Lawn Closure ...",
    "start: 2026-01-01T00:00",
    "borough: Manhattan",
    "type: Special Event",
    "location: Central Park",
    "→ A1 structured feed(dense)",
  ], C.blue);
  card(s, M, 4.35, CW, 2.35);
  sec(s, M + 0.15, 4.5, 6, "as-of feature snapshot 예시", "STEP 04 OUTPUT");
  s.addText([
    { text: "zone_id · forecast_cutoff · feature_version 와 함께 numeric feature가 저장됩니다:", options: { color: C.tx, breakLine: true } },
    { text: "event_count_6h_by_type · source_weighted_severity · distance_decayed_impact · time_to_event_start · neighbor_zone_impact · capacity_shock_exposure …", options: { color: C.txHi, fontFace: MONO, fontSize: 9.5, breakLine: true } },
    { text: "", options: { breakLine: true, fontSize: 6 } },
    { text: "규칙  ", options: { color: C.amber, bold: true, fontFace: MONO, fontSize: 9.5 } },
    { text: "available_at = max(published_at, first_seen_at) ≤ forecast_cutoff 인 event만 반영 → 14:01 기사(article)는 14:00 예측에 기여 0 (leakage 회귀 테스트).", options: { color: C.tx } },
  ], { x: M + 0.15, y: 4.85, w: CW - 0.3, h: 1.7, fontFace: SANS, fontSize: 10.5, align: "left", margin: 0, valign: "top", lineSpacingMultiple: 1.06 });
  foot(s, "예시는 curated fixture — live 데이터로 표시하지 않음", "provenance·evidence span 항상 보존");
})();

/* ============ 6 · 데이터 해석 ============ */
(() => {
  const s = S("06 / 12");
  head(s, "데이터 해석 — 수요의 성질과 함의", "DATA INTERPRETATION");
  kpiRow(s, 1.5, [
    ["2.7", "departures 평균(중앙값 2, 최대 87)", C.amber],
    ["20.2%", "0인 시간 비중 (0-inflated)", C.amber],
    ["64%", "값 ≤ 2 인 시간 (sparse count)", C.amber],
    ["0~12", "zone별 평균 규모 편차(극단)", C.teal],
    ["168h", "가장 강한 주간 seasonality lag", C.teal],
  ]);
  sec(s, M, 2.7, 6, "관찰", "WHAT THE DATA SAYS");
  s.addText(bul([
    [{ t: "간헐적 count 수요 — 0이 많고 heavy-tail, 큰 값이 드묾.", }],
    [{ t: "zone 규모가 0~12로 제각각 → scale-free 지표 필수.", }],
    [{ t: "단기 지속성(직전 시간)이 가장 강하고, 주간(168h)·일간(24h) 순.", }],
    [{ t: "평일/주말 차이는 총량보다 timing(저녁 러시)에서 옴.", }],
  ], C.amber), { x: M, y: 3.05, w: 6.1, h: 3.4, fontFace: SANS, fontSize: 12, align: "left", margin: 0, valign: "top" });
  sec(s, 6.95, 2.7, 6, "설계에 준 함의", "DESIGN IMPLICATIONS");
  s.addText(bul([
    [{ t: "지표: ", b: true, c: C.txHi }, { t: "MAPE 폭발 → WAPE(합산 정규화)+MASE(naive 대비)+OCS(비대칭 비용)." }],
    [{ t: "모델: ", b: true, c: C.txHi }, { t: "lag/rolling/calendar tabular feature → tree 계열이 적합, GNN 선행 불필요." }],
    [{ t: "leakage: ", b: true, c: C.txHi }, { t: "rolling 창은 shift 후 집계, 현재값이 자기 lag에 못 들어감." }],
    [{ t: "event: ", b: true, c: C.txHi }, { t: "sparse+coincident면 신호가 약함 → source density·timing이 관건." }],
  ], C.teal), { x: 6.95, y: 3.05, w: 5.85, h: 3.4, fontFace: SANS, fontSize: 12, align: "left", margin: 0, valign: "top" });
  foot(s, "출처: EDA + reports/phase06_results.json", "");
})();

/* ============ 7 · 모델 & 사용 이유 ============ */
(() => {
  const s = S("07 / 12");
  head(s, "모델 & 사용 이유", "MODELS & RATIONALE");
  const cols = [{ w: 3.1, label: "모델" }, { w: 4.9, label: "역할" }, { w: 4.33, label: "선택 이유" }];
  table(s, M, 1.55, cols, [
    [[{ t: "B0 Seasonal-Naive", b: true, c: C.txHi }], "ŷ = 지난주 같은 시각(168h)", "정직성 바닥·MASE 분모. 이걸 못 이기면 무의미"],
    [[{ t: "HistGradientBoosting", b: true, c: C.amber }], "promoted 예측 모델(전 zone 공통)", "sparse count·tabular lag에 강함, 빠르고 robust, feature 지배적"],
    [[{ t: "KNN / ExtraTrees 등", b: true, c: C.txHi }], "GridSearch 후보 zoo", "CV로 공정 선택 — 알고리즘보다 feature가 성능 좌우 확인"],
    [[{ t: "LLM (Claude/mock)", b: true, c: C.violet }], "event 추출·routing·설명", "숫자 예측 X — 비정형→구조화가 강점, typed-tool로 grounding"],
    [[{ t: "MILP / MPC", b: true, c: C.good }], "rebalancing 최적화", "정수·capacity 제약 정확 최적, MPC는 forecast로 look-ahead"],
    [[{ t: "GNN / Transformer", b: true, c: C.txLo }], "(보류)", "ablation·leakage 통과 전 선행 금지(§11.1) — 아직 근거 없음"],
  ], { rowH: 0.62, fs: 10 });
  card(s, M, 5.55, CW, 1.15, C.violet);
  s.addText([{ text: "왜 LLM이 숫자를 만들지 않나  ", options: { color: C.violet, bold: true, fontFace: MONO, fontSize: 10 } },
    { text: "LLM은 hallucination 위험이 있어 demand·price·profit을 직접 계산하지 않습니다. 대신 event를 구조화(evidence 필수)하고, Copilot 답변의 모든 숫자는 typed tool 결과에서만 나옵니다 — 근거 없는 숫자는 reject. 이것이 신뢰성과 감사가능성을 동시에 보장합니다.",
      options: { color: C.tx } }],
    { x: M + 0.15, y: 5.7, w: CW - 0.3, h: 0.9, fontFace: SANS, fontSize: 10.5, align: "left", margin: 0, valign: "top", lineSpacingMultiple: 1.05 });
  foot(s, "구현 순서: B0 → tree baseline → event-aware → (검증 후) 고급 모델", "");
})();

/* ============ 8 · 수요예측 판별 ============ */
(() => {
  const s = S("08 / 12");
  head(s, "수요예측을 어떻게 판별했나", "HOW FORECASTS ARE JUDGED");
  sec(s, M, 1.5, 6, "평가 프로토콜", "PROTOCOL");
  s.addText(bul([
    [{ t: "grain: H3 zone × local hour, target = departures/arrivals/net_flow", }],
    [{ t: "split: rolling-origin / expanding-window (random K-fold 금지), seed 42", }],
    [{ t: "event-window와 overall을 분리 보고, 모든 ablation은 동일 cutoff", }],
    [{ t: "재현: make v2-holdout → h3_multiholdout.json (windows=3)", }],
  ], C.amber), { x: M, y: 1.85, w: 6.1, h: 2.5, fontFace: SANS, fontSize: 11.5, align: "left", margin: 0, valign: "top" });
  sec(s, 6.95, 1.5, 6, "지표 정의", "METRICS");
  s.addText([
    { text: "WAPE", options: { color: C.txHi, bold: true, fontFace: MONO, fontSize: 10 } },
    { text: " = Σ|y−ŷ| / Σ|y|  (scale-free, 0에 robust) — 대표값", options: { breakLine: true, color: C.tx } },
    { text: "MASE", options: { color: C.txHi, bold: true, fontFace: MONO, fontSize: 10 } },
    { text: " = MAE / naive-MAE  ( <1 이면 naive를 이김 )", options: { breakLine: true, color: C.tx } },
    { text: "OCS", options: { color: C.txHi, bold: true, fontFace: MONO, fontSize: 10 } },
    { text: " = (c_short·부족 + c_over·과잉)/Σy  (비대칭 3:1)", options: { breakLine: true, color: C.tx } },
    { text: "peak-dir / bias", options: { color: C.txHi, bold: true, fontFace: MONO, fontSize: 10 } },
    { text: " = 방향 적중·체계적 과소예측(품절 위험)", options: { color: C.tx } },
  ], { x: 6.95, y: 1.85, w: 5.85, h: 2.5, fontFace: SANS, fontSize: 11.5, align: "left", margin: 0, valign: "top", lineSpacingMultiple: 1.15 });

  const cols = [{ w: 4.0, label: "model" }, { w: 2.1, label: "test WAPE" }, { w: 2.1, label: "MASE" }, { w: 4.13, label: "비고" }];
  table(s, M, 4.35, cols, [
    [[{ t: "B0 Seasonal-Naive", c: C.txLo }], [{ t: "0.6584", m: true }], [{ t: "1.0125", m: true }], "정직성 바닥"],
    [[{ t: "HistGradientBoosting (v2 promoted)", b: true, c: C.amber }], [{ t: "0.4828±0.0030", m: true, c: C.amber }], [{ t: "0.7996", m: true, c: C.good }], "H3 multi-holdout, naive를 이김"],
    [[{ t: "KNN (v1 CV-선택)", c: C.txHi }], [{ t: "0.5161", m: true }], [{ t: "0.7936", m: true }], "v1 JC June, 프로토콜대로 CV 선택"],
  ], { rowH: 0.5, fs: 10 });
  foot(s, "판별 기준: MASE<1(naive 우위) + rolling-origin 재현 + event-window 별도", "artifact: reports/v2/holdout/*");
})();

/* ============ 9 · 정답지 ============ */
(() => {
  const s = S("09 / 12");
  head(s, "정답지(ground truth)는 무엇인가", "WHAT IS THE GROUND TRUTH");
  const cols = [{ w: 3.2, label: "무엇을 판별" }, { w: 5.2, label: "정답지(label)" }, { w: 3.93, label: "만드는 방법" }];
  table(s, M, 1.55, cols, [
    [[{ t: "수요 예측", b: true, c: C.txHi }], "실제 발생한 trip 수 (departures/arrivals/net_flow)", "trip을 H3 zone×local hour로 집계 (America/New_York)"],
    [[{ t: "event/LLM 가치", b: true, c: C.amber }], "held-out WAPE (LLM-active subset) + block-bootstrap CI", "LFV metric — 동일 cutoff, active zone-hour만"],
    [[{ t: "rebalancing", b: true, c: C.good }], "Oracle net (realized demand 사용, offline 상한)", "regret = Oracle − policy (≥0 by construction)"],
    [[{ t: "pricing", b: true, c: C.good }], "guardrail 위반 수 + A/A null (CI∋0)", "bounded 규칙 위반 카운트 + negative control"],
    [[{ t: "Copilot", b: true, c: C.teal }], "gold Q&A + typed-tool 값 + RAGAS faithfulness", "질문셋 정답 + 답 숫자의 tool-근거 일치"],
  ], { rowH: 0.62, fs: 10 });
  card(s, M, 5.35, CW, 1.35, C.crit);
  s.addText([{ text: "정답지 무결성 규칙  ", options: { color: C.crit, bold: true, fontFace: MONO, fontSize: 10 } },
    { text: "① 재고(inventory) snapshot 차이를 수요 label로 쓰지 않습니다(금지). ② label은 항상 forecast_cutoff 이후에 관측되는 것이어야 하고, event는 available_at ≤ cutoff 일 때만 feature화 → 미래 누수 차단. ③ delayed label이 도착해야 pending→measured로 확정(available_at > cutoff면 leakage_rejected).",
      options: { color: C.tx } }],
    { x: M + 0.15, y: 5.48, w: CW - 0.3, h: 1.1, fontFace: SANS, fontSize: 10.5, align: "left", margin: 0, valign: "top", lineSpacingMultiple: 1.05 });
  foot(s, "live 실측 label은 아직 미수집 → 해당 항목은 blocked_data로 정직 표기", "");
})();

/* ============ 10 · LLM VALUE 판별 결과 ============ */
(() => {
  const s = S("10 / 12");
  head(s, "핵심 질문 — LLM은 예측 가치를 더했나", "LLM VALUE VERDICT (V2-03)");
  const cols = [{ w: 3.4, label: "ablation arm" }, { w: 2.2, label: "WAPE" }, { w: 6.73, label: "판정" }];
  table(s, M, 1.5, cols, [
    [[{ t: "A0  demand + calendar", b: true, c: C.txHi }], [{ t: "0.0908", m: true }], "baseline (event 없음)"],
    [[{ t: "A1  + structured 허가 feed", b: true, c: C.good }], [{ t: "0.0883", m: true, c: C.good }], [{ t: "MEANINGFUL_POSITIVE +2.69% (active subset, CI>0) — 도움", c: C.good }]],
    [[{ t: "A2  + LLM-from-news", b: true, c: C.crit }], [{ t: "0.0905", m: true, c: C.crit }], [{ t: "negative_lift · net −$17,789 — news는 redundant", c: C.crit }]],
  ], { rowH: 0.56, fs: 10.5 });
  sec(s, M, 3.65, 6, "왜 news는 실패했나 (root cause)", "PROVEN, NOT ASSUMED");
  s.addText(bul([
    [{ t: "feature가 도우려면 source가 4조건 동시 충족: ", }, ],
    [{ t: "dense + precise-time + precise-location + forward-looking", c: C.amber, b: true }],
    [{ t: "news는 전부 미충족 (23건 중 forward-looking 2건).", }],
    [{ t: "density curve + quality ablation으로 '단순 데이터부족' 아님을 입증.", }],
  ], C.amber), { x: M, y: 4.0, w: 6.1, h: 2.6, fontFace: SANS, fontSize: 11, align: "left", margin: 0, valign: "top" });
  card(s, 6.95, 3.9, 5.88, 2.75, C.teal);
  s.addText([{ text: "그럼 방법이 틀렸나? 아니오.", options: { color: C.teal, bold: true, breakLine: true, fontSize: 11.5 } },
    { text: "", options: { breakLine: true, fontSize: 5 } },
    { text: "synthetic ceiling", options: { color: C.txHi, bold: true, fontFace: MONO, fontSize: 10 } },
    { text: " (simulated): 4조건을 만족하는 event를 주입하면 LLM post-correction ", options: { color: C.tx } },
    { text: "+10.43%", options: { color: C.good, bold: true } },
    { text: " → 방법은 유효, 한계는 news라는 source.", options: { color: C.tx, breakLine: true } },
    { text: "", options: { breakLine: true, fontSize: 5 } },
    { text: "결론: ", options: { color: C.amber, bold: true } },
    { text: "예측 lift의 실체는 structured feed. LLM의 실측 가치는 Copilot(routing·grounding·설명)에 있음.", options: { color: C.tx } },
  ], { x: 7.12, y: 4.08, w: 5.55, h: 2.45, fontFace: SANS, fontSize: 10.8, align: "left", margin: 0, valign: "top", lineSpacingMultiple: 1.05 });
  foot(s, "artifact: incremental_value_borough·density_curve·quality_ablation·synthetic_ceiling", "borough-hour grain · test 2026-05");
})();

/* ============ 11 · 의사결정 레이어 ============ */
(() => {
  const s = S("11 / 12");
  head(s, "의사결정 레이어 — 예측을 행동으로", "DECISION LAYER");
  // MPC bars card
  card(s, M, 1.55, 5.9, 2.7);
  s.addText([{ text: "MPC 정책 비교 ", options: { color: C.txHi, bold: true } },
    { text: "— ledger total_cost (낮을수록 좋음)", options: { color: C.txLo, fontSize: 9 } }],
    { x: M + 0.2, y: 1.7, w: 5.5, h: 0.3, fontFace: SANS, fontSize: 11, align: "left", margin: 0, valign: "middle" });
  const bars = [["No-Action", 1127, C.txLo], ["Greedy", 1155, C.txLo], ["MILP", 1087, C.txLo], ["MPC ★", 740, C.amber], ["Oracle", 719, C.teal]];
  const maxV = 1155, bx = 2.05, bw = 3.0, by0 = 2.2, bh = 0.2, bgap = 0.36;
  bars.forEach((b, i) => {
    const y = by0 + i * bgap;
    s.addText(b[0], { x: M + 0.2, y: y - 0.03, w: 1.2, h: 0.24, fontFace: MONO, fontSize: 9, color: C.txLo, align: "left", margin: 0, valign: "middle" });
    s.addShape(p.ShapeType.roundRect, { x: bx, y, w: bw, h: bh, rectRadius: 0.03, fill: { color: C.panel2 }, line: { color: C.panel2, width: 0 } });
    s.addShape(p.ShapeType.roundRect, { x: bx, y, w: bw * (b[1] / maxV), h: bh, rectRadius: 0.03, fill: { color: b[2] }, line: { color: b[2], width: 0 } });
    s.addText(String(b[1]), { x: bx + bw + 0.1, y: y - 0.03, w: 0.7, h: 0.24, fontFace: MONO, fontSize: 9.5, color: C.txHi, align: "left", margin: 0, valign: "middle" });
  });
  // pricing + copilot cards
  card(s, 6.6, 1.55, 6.23, 1.28, C.good);
  s.addText([{ text: "Pricing (simulated)  ", options: { color: C.good, bold: true, fontFace: MONO, fontSize: 10 } },
    { text: "bounded surge + guardrail + A/A dry-run", options: { color: C.txLo, fontSize: 9, breakLine: true } },
    { text: "576 zone-hour에서 위반 0 · budget 준수 · A/A CI∋0 (유효 null) · shadow quote만(실제 청구 없음)", options: { color: C.tx } }],
    { x: 6.78, y: 1.68, w: 5.9, h: 1.05, fontFace: SANS, fontSize: 10, align: "left", margin: 0, valign: "top", lineSpacingMultiple: 1.05 });
  card(s, 6.6, 2.97, 6.23, 1.28, C.teal);
  s.addText([{ text: "Decision Copilot (offline_benchmark)  ", options: { color: C.teal, bold: true, fontFace: MONO, fontSize: 10, breakLine: true } },
    { text: "typed-tool routing 1.0 · hallucination 0 · RAGAS faithfulness 1.0 · answer_relevancy 0.985 · trip-plan faithfulness 1.0. 숫자는 tool 결과만, 근거 없으면 refuse.", options: { color: C.tx } }],
    { x: 6.78, y: 3.1, w: 5.9, h: 1.05, fontFace: SANS, fontSize: 10, align: "left", margin: 0, valign: "top", lineSpacingMultiple: 1.05 });
  card(s, M, 4.5, CW, 2.2, C.amber);
  sec(s, M + 0.18, 4.66, 8, "해석 — 왜 MPC인가", "READ");
  s.addText(bul([
    [{ t: "MPC가 regret 21.6 (Oracle의 ~3%)로 best feasible — forecast look-ahead가 핵심.", }],
    [{ t: "Oracle은 realized demand를 쓰는 offline 상한 → 배포 불가, 비교 기준일 뿐.", }],
    [{ t: "모든 금액은 versioned assumption에 조건부(simulated), 단위 수량만 measured — 부호는 9/9 설정에서 안정.", }],
  ], C.amber), { x: M + 0.18, y: 5.0, w: CW - 0.4, h: 1.6, fontFace: SANS, fontSize: 11, align: "left", margin: 0, valign: "top" });
  foot(s, "artifact: mpc/policy_comparison · pricing/* · copilot/*", "");
})();

/* ============ 12 · 고도화 로드맵 ============ */
(() => {
  const s = S("12 / 12");
  head(s, "고도화 방법 — 다음 투자처", "ADVANCEMENT ROADMAP");
  const cols = [{ w: 0.6, label: "#" }, { w: 4.2, label: "과제" }, { w: 4.6, label: "기대 효과" }, { w: 2.93, label: "우선순위" }];
  table(s, M, 1.5, cols, [
    [[{ t: "1", m: true, c: C.amber }], [{ t: "Event geocoding → H3-grain graph 검증", b: true, c: C.txHi }], "현재 blocked_data(borough-tag) 해소 → graph 기여 공정 재측정", [{ t: "HIGH · 직접", c: C.good, b: true }]],
    [[{ t: "2", m: true, c: C.amber }], [{ t: "forward-looking dense source 확대", b: true, c: C.txHi }], "transit alert·venue schedule·permit → LLM value 4조건 충족", [{ t: "HIGH", c: C.good, b: true }]],
    [[{ t: "3", m: true, c: C.amber }], [{ t: "Calibrated intervals (p10/p50/p90)", b: true, c: C.txHi }], "현재 없음 → 재고 리스크·안전재고 의사결정 강화", [{ t: "MED", c: C.amber, b: true }]],
    [[{ t: "4", m: true, c: C.amber }], [{ t: "Spatial / GNN·temporal 모델", b: true, c: C.txHi }], "ablation·leakage 통과 후 도입 — feature 지배 구조 넘어설 때", [{ t: "MED · 조건부", c: C.amber, b: true }]],
    [[{ t: "5", m: true, c: C.amber }], [{ t: "Live label 수집 + delayed-label 재학습", b: true, c: C.txHi }], "pending→measured 확정, drift 감지 (online bandit은 금지)", [{ t: "MED", c: C.amber, b: true }]],
    [[{ t: "6", m: true, c: C.amber }], [{ t: "Research 심화: RL · Quantum", b: true, c: C.txLo }], "learned policy·QUBO — 완성 조건 아님, product 격리 유지", [{ t: "LOW · research", c: C.txLo }]],
  ], { rowH: 0.58, fs: 9.8 });
  card(s, M, 5.6, CW, 1.1, C.teal);
  s.addText([{ text: "한 줄 요약  ", options: { color: C.teal, bold: true, fontFace: MONO, fontSize: 10 } },
    { text: "가장 큰 지렛대는 ‘더 똑똑한 모델’이 아니라 ‘조건을 만족하는 source’입니다 — geocoding으로 H3 graph를 열고, forward-looking dense feed를 확보하면 synthetic ceiling(+10.43%)에서 본 잠재 이득을 실측으로 전환할 수 있습니다.",
      options: { color: C.tx } }],
    { x: M + 0.15, y: 5.73, w: CW - 0.3, h: 0.85, fontFace: SANS, fontSize: 10.5, align: "left", margin: 0, valign: "top", lineSpacingMultiple: 1.05 });
  foot(s, "ShockFlow AI — CTO Technical Review · 끝", "measured · simulated · blocked · research 구분 유지");
})();

p.writeFile({ fileName: "/tmp/claude-0/-home-user-AI-Pro-project/13a719e5-acff-5289-a79f-baead6ecad81/scratchpad/ShockFlow_AI_CTO_review.pptx" })
  .then(f => console.log("WROTE", f));

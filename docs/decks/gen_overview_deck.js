const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.defineLayout({ name: "W", width: 13.333, height: 7.5 });
p.layout = "W";

// --- palette (dark ops console) ---
const C = {
  ground: "0C1220", panel: "141E30", panel2: "1B2740", line: "2A3A54",
  txHi: "EEF3FB", tx: "AEBCD4", txLo: "7E8DA8",
  amber: "F5A02B", amberDim: "3A2A10", teal: "3AC6D4", tealDim: "0E2A33",
  good: "43C08A", crit: "F0656A", violet: "9C8BF0",
};
const SANS = "Calibri", MONO = "Courier New";
const sh = () => ({ type: "outer", color: "000000", opacity: 0.45, blur: 10, offset: 3, angle: 90 });

function bg(s) { s.background = { color: C.ground }; }
function eyebrow(s, x, y, txt) {
  s.addShape(p.ShapeType.ellipse, { x, y: y + 0.03, w: 0.1, h: 0.1, fill: { color: C.amber } });
  s.addText(txt, { x: x + 0.18, y: y - 0.08, w: 11, h: 0.3, fontFace: MONO, fontSize: 10.5,
    color: C.txLo, charSpacing: 2, align: "left", margin: 0, valign: "middle" });
}
function sechead(s, x, y, w, ko, en) {
  s.addText([{ text: ko, options: { color: C.amber, bold: true } },
             { text: en ? "  " + en : "", options: { color: C.txLo, bold: false } }],
    { x, y, w, h: 0.3, fontFace: MONO, fontSize: 11.5, charSpacing: 1.5, align: "left", margin: 0, valign: "middle" });
}
// numbered bullet list -> run array (pairs of runs per line)
function bullets(items, numColor) {
  const runs = [];
  items.forEach((it, i) => {
    runs.push({ text: (i + 1) + "  ", options: { color: numColor, bold: true, fontFace: MONO, fontSize: 11 } });
    runs.push({ text: it, options: { color: C.tx, bold: false, breakLine: true } });
    runs.push({ text: "", options: { breakLine: true, fontSize: 4 } }); // spacer line
  });
  return runs;
}

/* ============================ SLIDE 1 — MACRO ============================ */
const s1 = p.addSlide(); bg(s1);
// page tag
s1.addText("01 · 거시 / MACRO", { x: 10.3, y: 0.32, w: 2.7, h: 0.3, fontFace: MONO, fontSize: 10,
  color: C.txLo, align: "right", margin: 0, valign: "middle" });
eyebrow(s1, 0.55, 0.42, "EVENT-AWARE URBAN MOBILITY · CITI BIKE / NYC");
s1.addText([{ text: "ShockFlow ", options: { color: C.txHi } }, { text: "AI", options: { color: C.amber } }],
  { x: 0.5, y: 0.62, w: 9, h: 0.8, fontFace: SANS, fontSize: 40, bold: true, charSpacing: 0, align: "left", margin: 0 });
s1.addText(
  "시간정보가 붙은 event에서 수요 shock를 감지 → 추적 가능한 graph feature로 변환 → 예측에 준 model-attributed 영향(입증된 인과 아님)을 정량화 → 실행 가능한 rebalancing 조치로 연결.",
  { x: 0.52, y: 1.42, w: 12.3, h: 0.55, fontFace: SANS, fontSize: 13, color: C.tx, align: "left", margin: 0, lineSpacingMultiple: 1.05 });

// workflow strip
const nodes = [
  ["INPUT 1", "Citi Bike 수요 이력", C.teal], ["INPUT 2", "timestamped news / event", C.teal],
  ["INPUT 3", "station 재고 · GBFS", C.teal], ["STEP 1·2", "LLM 추출 → Neo4j graph", C.amber],
  ["STEP 3", "as-of graph feature", C.amber], ["STEP 4", "H3 zone-hour forecast", C.amber],
  ["STEP 5·6", "설명·scenario → rebalancing", C.good],
];
const nX0 = 0.5, nW = 1.66, nGap = 0.13, nY = 2.12, nH = 0.95;
nodes.forEach((n, i) => {
  const x = nX0 + i * (nW + nGap);
  const tint = n[2] === C.teal ? C.tealDim : (n[2] === C.amber ? C.amberDim : "10261C");
  s1.addShape(p.ShapeType.roundRect, { x, y: nY, w: nW, h: nH, rectRadius: 0.07,
    fill: { color: C.panel2 }, line: { color: n[2], width: 1 } });
  s1.addText(n[0], { x: x + 0.02, y: nY + 0.08, w: nW - 0.04, h: 0.24, fontFace: MONO, fontSize: 8,
    color: n[2], align: "center", margin: 0, valign: "middle", charSpacing: 1 });
  s1.addText(n[1], { x: x + 0.06, y: nY + 0.32, w: nW - 0.12, h: 0.55, fontFace: SANS, fontSize: 10,
    bold: true, color: C.txHi, align: "center", margin: 0, valign: "middle", lineSpacingMultiple: 0.95 });
  if (i < nodes.length - 1) s1.addText("›", { x: x + nW - 0.02, y: nY, w: nGap + 0.04, h: nH,
    fontFace: SANS, fontSize: 14, color: C.txLo, align: "center", valign: "middle", margin: 0 });
});

// domain-term gloss (한 번만): 도메인 용어 풀이
s1.addText([{ text: "용어  ", options: { color: C.amber, bold: true, fontFace: MONO, fontSize: 8.5 } },
  { text: "H3 zone = 동네 블록 단위(육각 격자 res 9, ~170 m) · borough = 뉴욕 자치구(시 행정구역)", options: { color: C.txLo, fontSize: 8.5 } }],
  { x: 0.5, y: 3.16, w: 12.3, h: 0.22, fontFace: SANS, align: "left", margin: 0, valign: "middle" });

// two columns
const colY = 3.42, colBot = 7.15;
// left column
sechead(s1, 0.55, colY, 6, "BACKGROUND", "배경 / 문제");
s1.addText([
  { text: "운영 손실의 대부분은 ", options: { color: C.tx } }, { text: "stockout(품절)", options: { color: C.txHi, bold: true } },
  { text: " · ", options: { color: C.tx } }, { text: "overflow(dock 초과)", options: { color: C.txHi, bold: true } },
  { text: "에서 발생 — rider 이탈과 rebalancing 트럭 비용.", options: { color: C.tx, breakLine: true } },
  { text: "event·교통장애·날씨 등 ", options: { color: C.tx } }, { text: "irregular demand shock", options: { color: C.txHi, bold: true } },
  { text: "에 기존 예측은 취약하고, LLM/뉴스 효과는 검증 없이 과장되기 쉬움.", options: { color: C.tx } },
], { x: 0.55, y: colY + 0.34, w: 5.9, h: 1.05, fontFace: SANS, fontSize: 12, align: "left", margin: 0, lineSpacingMultiple: 1.05 });

sechead(s1, 0.55, colY + 1.5, 6, "BUSINESS", "사업 포인트");
s1.addText(bullets([
  "운영비 절감 — 정확한 forecast → shortage/overflow·이동 비용↓",
  "LLM 가치의 profit 환산 — LLM 비용을 제한 순가치를 측정",
  "Operator Decision Copilot — 근거 기반, 숫자 hallucination 0",
  "Rider trip planner — 대여·반납 station + 도보 안내",
], C.teal), { x: 0.55, y: colY + 1.84, w: 5.95, h: 1.9, fontFace: SANS, fontSize: 11.5, align: "left", margin: 0, valign: "top" });

// right column
sechead(s1, 6.95, colY, 6, "DIFFERENTIATION", "차별성");
s1.addText(bullets([
  "End-to-end 추적성 — Article→Event→Zone→Feature→delta→action",
  "Temporal correctness — available_at ≤ cutoff, leakage 방지",
  "Honesty 계약 — claim_status + ResultEnvelope, null도 정직 보고",
  "LLM 경계 — 숫자는 typed tool에서만 (LLM은 구조화·설명만)",
  "Graph 실기여 — Neo4j event feature가 forecasting에 사용",
], C.amber), { x: 6.95, y: colY + 0.34, w: 5.85, h: 2.4, fontFace: SANS, fontSize: 11.5, align: "left", margin: 0, valign: "top" });

s1.addShape(p.ShapeType.roundRect, { x: 6.95, y: colBot - 0.72, w: 5.85, h: 0.62, rectRadius: 0.06,
  fill: { color: C.panel }, line: { color: C.line, width: 1 } });
s1.addText([
  { text: "모든 결과 라벨  ", options: { color: C.amber, bold: true, fontFace: MONO, fontSize: 9.5 } },
  { text: "run_id · artifact_id · mode · claim_status · freshness", options: { color: C.txHi, fontFace: MONO, fontSize: 9.5, breakLine: true } },
  { text: "9-value taxonomy — 무엇을 주장할 수 있는지 코드가 강제", options: { color: C.txLo, fontFace: SANS, fontSize: 9 } },
], { x: 7.1, y: colBot - 0.66, w: 5.6, h: 0.5, align: "left", margin: 0, valign: "middle", lineSpacingMultiple: 1.0 });

s1.addText("ShockFlow AI — Citi Bike / NYC · H3 zone × local hour", { x: 0.5, y: 7.16, w: 8, h: 0.25,
  fontFace: MONO, fontSize: 8.5, color: C.txLo, align: "left", margin: 0 });
s1.addText("V2_COMPLETE · 31 artifacts · 3 gates PASS", { x: 6.8, y: 7.16, w: 6.0, h: 0.25,
  fontFace: MONO, fontSize: 8.5, color: C.good, align: "right", margin: 0 });

/* ============================ SLIDE 2 — MICRO ============================ */
const s2 = p.addSlide(); bg(s2);
s2.addText("02 · 미시 / MICRO", { x: 10.3, y: 0.32, w: 2.7, h: 0.3, fontFace: MONO, fontSize: 10,
  color: C.txLo, align: "right", margin: 0, valign: "middle" });
eyebrow(s2, 0.55, 0.42, "WORKFLOW별 기술 · 달성 지표 · 상세");
s2.addText([{ text: "단계별 기술 & ", options: { color: C.txHi } }, { text: "측정 지표", options: { color: C.amber } }],
  { x: 0.5, y: 0.62, w: 10, h: 0.55, fontFace: SANS, fontSize: 26, bold: true, align: "left", margin: 0 });

// KPI tiles
const kpis = [
  ["0.4828", "H3 holdout WAPE · MASE 0.7996 (naive↑)", C.amber],
  ["+$103k", "promoted net vs no-action · 9/9 부호+", C.good],
  ["21.6", "MPC regret vs Oracle · best feasible", C.amber],
  ["0", "Copilot halluc · pricing guardrail 위반", C.teal],
  ["31", "artifacts · final audit V2_COMPLETE", C.good],
];
const kX0 = 0.5, kW = 2.44, kGap = 0.11, kY = 1.28, kH = 0.9;
kpis.forEach((k, i) => {
  const x = kX0 + i * (kW + kGap);
  s2.addShape(p.ShapeType.roundRect, { x, y: kY, w: kW, h: kH, rectRadius: 0.06,
    fill: { color: C.panel2 }, line: { color: C.line, width: 1 } });
  s2.addText(k[0], { x: x + 0.14, y: kY + 0.08, w: kW - 0.28, h: 0.42, fontFace: MONO, fontSize: 21,
    bold: true, color: k[2], align: "left", margin: 0, valign: "middle" });
  s2.addText(k[1], { x: x + 0.15, y: kY + 0.5, w: kW - 0.3, h: 0.36, fontFace: SANS, fontSize: 8.5,
    color: C.txLo, align: "left", margin: 0, valign: "top", lineSpacingMultiple: 0.95 });
});

// stage table
const tX = 0.5, tY = 2.34, cW = [2.15, 5.75, 4.4];
const cX = [tX, tX + cW[0], tX + cW[0] + cW[1]];
const heads = ["단계", "핵심 기술", "달성 지표 (artifact)"];
heads.forEach((h, i) => s2.addText(h, { x: cX[i] + 0.08, y: tY, w: cW[i] - 0.1, h: 0.28,
  fontFace: MONO, fontSize: 9, color: C.txLo, charSpacing: 1, align: "left", margin: 0, valign: "middle" }));
s2.addShape(p.ShapeType.line, { x: tX, y: tY + 0.3, w: cW[0] + cW[1] + cW[2], h: 0, line: { color: C.amber, width: 1 } });

const rows = [
  ["01", "Data collection", "trip CSV/ZIP · news JSONL · GBFS station_status, typed Pydantic contract",
    [{ text: "3 source 오프라인 재현 · schema hash / exclusion 기록", options: { color: C.tx } }]],
  ["02", "LLM event 추출", "provider interface + deterministic mock + real Claude, evidence-span 강제·Pydantic 검증",
    [{ text: "23 clean NYC events · 근거 없는 event ", options: { color: C.tx } }, { text: "0", options: { color: C.good, bold: true } }]],
  ["03", "Neo4j event graph", "Article/Event/Place/H3Zone/Station, parameterized Cypher, idempotent upsert",
    [{ text: "2,895 events / 6 zones · 재실행 시 node 증가 ", options: { color: C.tx } }, { text: "0", options: { color: C.good, bold: true } }]],
  ["04", "As-of graph feature", "half-life · distance decay · neighbor spillover — pure kernel, leakage-gated",
    [{ text: "14:01→14:00 leakage 회귀 통과 · deterministic", options: { color: C.tx } }]],
  ["05", "Forecasting", "HistGradientBoosting, rolling-origin H3 multi-holdout, LFV metric (+block-bootstrap CI)",
    [{ text: "WAPE 0.4828 · structured ", options: { color: C.tx } }, { text: "+2.69%", options: { color: C.good, bold: true } },
     { text: " · news ", options: { color: C.tx } }, { text: "null −$17,789", options: { color: C.crit, bold: true } }]],
  ["06", "설명 · Copilot", "GraphRAG typed-tool (숫자는 tool 결과만), RAGAS non-LLM retrieval + faithfulness",
    [{ text: "routing 1.0 · halluc ", options: { color: C.tx } }, { text: "0", options: { color: C.good, bold: true } },
     { text: " · faith 1.0 · relevancy 0.985", options: { color: C.tx } }]],
  ["07", "Rebalancing · pricing", "Greedy→MILP→MPC→Oracle (profit/regret ledger), bounded pricing + guardrail + A/A",
    [{ text: "MPC 740 / regret 21.6 · 위반 ", options: { color: C.tx } }, { text: "0", options: { color: C.good, bold: true } },
     { text: " /576 zone-h", options: { color: C.tx } }]],
];
const rY0 = tY + 0.36, rH = 0.40;
rows.forEach((r, i) => {
  const y = rY0 + i * rH;
  if (i % 2 === 1) s2.addShape(p.ShapeType.rect, { x: tX, y: y - 0.02, w: cW[0] + cW[1] + cW[2], h: rH, fill: { color: C.panel } , line: { color: C.panel, width: 0 } });
  s2.addText([{ text: r[0] + "  ", options: { color: C.amber, bold: true, fontFace: MONO, fontSize: 9 } },
              { text: r[1], options: { color: C.txHi, bold: true } }],
    { x: cX[0] + 0.08, y, w: cW[0] - 0.12, h: rH, fontFace: SANS, fontSize: 9.5, align: "left", margin: 0, valign: "middle", lineSpacingMultiple: 0.9 });
  s2.addText(r[2], { x: cX[1] + 0.08, y, w: cW[1] - 0.16, h: rH, fontFace: SANS, fontSize: 9, color: C.tx,
    align: "left", margin: 0, valign: "middle", lineSpacingMultiple: 0.9 });
  s2.addText(r[3], { x: cX[2] + 0.08, y, w: cW[2] - 0.12, h: rH, fontFace: MONO, fontSize: 9,
    align: "left", margin: 0, valign: "middle", lineSpacingMultiple: 0.95 });
});

// bottom: MPC bars + v1/v2/research
const bY = rY0 + rows.length * rH + 0.12, cardH = 1.42;
s2.addShape(p.ShapeType.roundRect, { x: 0.5, y: bY, w: 4.55, h: cardH, rectRadius: 0.06, fill: { color: C.panel }, line: { color: C.line, width: 1 } });
s2.addText([{ text: "MPC 정책 비교 ", options: { color: C.txHi, bold: true } },
            { text: "— ledger total_cost, 낮을수록 좋음", options: { color: C.txLo, fontSize: 8.5 } }],
  { x: 0.68, y: bY + 0.1, w: 4.2, h: 0.25, fontFace: SANS, fontSize: 10, align: "left", margin: 0, valign: "middle" });
const bars = [["No-Action", 1127, C.txLo], ["Greedy", 1155, C.txLo], ["MILP", 1087, C.txLo], ["MPC ★", 740, C.amber], ["Oracle", 719, C.teal]];
const maxV = 1155, barX = 1.55, barW = 2.55, barY0 = bY + 0.42, barH = 0.14, barGap = 0.205;
bars.forEach((b, i) => {
  const y = barY0 + i * barGap;
  s2.addText(b[0], { x: 0.66, y: y - 0.03, w: 0.9, h: 0.2, fontFace: MONO, fontSize: 8, color: C.txLo, align: "left", margin: 0, valign: "middle" });
  s2.addShape(p.ShapeType.roundRect, { x: barX, y, w: barW, h: barH, rectRadius: 0.03, fill: { color: C.panel2 }, line: { color: C.panel2, width: 0 } });
  s2.addShape(p.ShapeType.roundRect, { x: barX, y, w: barW * (b[1] / maxV), h: barH, rectRadius: 0.03, fill: { color: b[2] }, line: { color: b[2], width: 0 } });
  s2.addText(String(b[1]), { x: barX + barW + 0.08, y: y - 0.03, w: 0.55, h: 0.2, fontFace: MONO, fontSize: 8.5, color: C.txHi, align: "left", margin: 0, valign: "middle" });
});

s2.addShape(p.ShapeType.roundRect, { x: 5.25, y: bY, w: 7.55, h: cardH, rectRadius: 0.06, fill: { color: C.panel }, line: { color: C.line, width: 1 } });
s2.addText([
  { text: "V1", options: { color: C.teal, bold: true, fontFace: MONO, fontSize: 8.5 } },
  { text: "  측정 모델·제품 — B0–B4 · dual-encoder recsys+reranker · switchback 실험 · anomaly · FAISS (test WAPE 0.5161 vs B0 0.658; MILP=exact, shortage 146→78).", options: { color: C.tx, breakLine: true } },
  { text: "", options: { breakLine: true, fontSize: 4 } },
  { text: "V2", options: { color: C.amber, bold: true, fontFace: MONO, fontSize: 8.5 } },
  { text: "  LLM net-value 검증 (V2-00…09) — H3 holdout · ledger · Rule vs LLM ablation · MPC · pricing · GraphRAG · monitoring. 완성=artifact 기반 → V2_COMPLETE.", options: { color: C.tx, breakLine: true } },
  { text: "", options: { breakLine: true, fontSize: 4 } },
  { text: "RESEARCH", options: { color: C.violet, bold: true, fontFace: MONO, fontSize: 8 } },
  { text: "  Quantum QUBO/QAOA · RL (PPO 202.9 / Q-learning 247.8, MPC 21.6 미달) — no advantage, product 차단.", options: { color: C.txLo } },
], { x: 5.42, y: bY + 0.11, w: 7.25, h: cardH - 0.22, fontFace: SANS, fontSize: 8.5, align: "left", margin: 0, valign: "top", lineSpacingMultiple: 0.98 });

s2.addText("모든 수치는 reports/v2/** committed artifact가 재현 · make v2-final → claim_matrix.json", { x: 0.5, y: 7.16, w: 12.3, h: 0.22,
  fontFace: MONO, fontSize: 8, color: C.txLo, align: "left", margin: 0 });

p.writeFile({ fileName: "/tmp/claude-0/-home-user-AI-Pro-project/13a719e5-acff-5289-a79f-baead6ecad81/scratchpad/ShockFlow_AI_overview.pptx" })
  .then(f => console.log("WROTE", f));

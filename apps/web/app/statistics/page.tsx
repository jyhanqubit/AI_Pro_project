"use client";

import { useState } from "react";
import Link from "next/link";
import { useReplay } from "../providers";
import { useApi } from "@/lib/useApi";
import {
  api,
  type AvailabilityLevel,
  type OperatorStatistics,
  type OperatorTimeline,
  type OpsAskResponse,
  type StationImportResponse,
  type TimelinePoint,
} from "@/lib/api";
import { signed } from "@/lib/format";

// Ops copilot: ask in natural language. Every fact comes from the same artifacts these dashboards
// render (/v2/operator/ask, deterministic + grounded); answers can deep-link to a screen.
const OPS_CHIPS = ["지금 현황", "부족 대여소", "수요 급증", "요금 상태"];

function OpsCopilot({ cutoff }: { cutoff: string | null }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<OpsAskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(query: string) {
    const text = query.trim();
    if (!text || !cutoff) return;
    setLoading(true);
    try {
      setRes(await api.opsAsk(text, cutoff));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card copilot">
      <h2>🛠 운영 도우미에게 물어보세요</h2>
      <div className="sub">
        대시보드와 동일한 데이터로 답합니다 (규칙 기반 · 오프라인 · 임의 SQL 없음).
      </div>
      <div className="searchbar" style={{ marginTop: 10 }}>
        <span className="search-icon" aria-hidden="true">💬</span>
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask(q)}
          placeholder="예: 지금 시스템 현황 어때? · 부족한 곳 어디야 · 요금 화면 열어"
          aria-label="운영 도우미 질문"
        />
        <button className="btn primary" onClick={() => ask(q)} disabled={loading || !cutoff}>
          {loading ? "…" : "물어보기"}
        </button>
      </div>
      <div className="copilot-chips">
        {OPS_CHIPS.map((c) => (
          <button
            key={c}
            className="chip"
            onClick={() => {
              setQ(c);
              void ask(c);
            }}
          >
            {c}
          </button>
        ))}
      </div>
      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}
      {res && (
        <div className={`copilot-answer ${res.supported ? "" : "unsupported"}`}>
          <p className="answer-text">{res.answer}</p>
          {res.link && (
            <Link href={res.link.href} className="btn primary ops-link">
              {res.link.label} →
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

// Event-local hour label (12..18) from an ISO cutoff, matching the replay preset buttons.
function hourLabel(iso: string): string {
  return iso.slice(11, 13);
}

// Operator statistics / analytics (V2 usability update).
// Real aggregations of the as-of replay state from /v2/operator/statistics: system inventory,
// availability distribution, shortage load, event mix, demand-delta spread, and a per-zone table.
// Every value is computed offline from the same pipeline the rest of the API uses — the demand
// delta is the labelled demo-heuristic forecast delta, not a measured Phase 06 model output.

const LEVEL_LABEL: Record<AvailabilityLevel, string> = {
  plenty: "넉넉",
  ok: "여유",
  tight: "빠듯",
  low: "곧 부족",
};
const LEVEL_ORDER: AvailabilityLevel[] = ["plenty", "ok", "tight", "low"];

function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "ok" | "low" | "up";
}) {
  return (
    <div className="card stat">
      <div className="sub">{label}</div>
      <div className={`metric ${tone === "ok" ? "ok-text" : tone === "low" ? "low-text" : ""}`}>
        {value}
      </div>
      {sub && <div className="muted small">{sub}</div>}
    </div>
  );
}

function StackBar({ counts, total }: { counts: Record<AvailabilityLevel, number>; total: number }) {
  return (
    <div>
      <div className="stackbar" role="img" aria-label="가용성 분포">
        {LEVEL_ORDER.map((lv) =>
          counts[lv] > 0 ? (
            <div
              key={lv}
              className={`stackseg ${lv}`}
              style={{ width: `${total ? (counts[lv] / total) * 100 : 0}%` }}
              title={`${LEVEL_LABEL[lv]} ${counts[lv]}곳`}
            />
          ) : null,
        )}
      </div>
      <div className="stack-legend">
        {LEVEL_ORDER.map((lv) => (
          <span key={lv} className="legend-item">
            <span className={`dot ${lv}`} /> {LEVEL_LABEL[lv]} {counts[lv]}
          </span>
        ))}
      </div>
    </div>
  );
}

function BarList({
  rows,
}: {
  rows: { label: string; value: number; display: string; tone?: string }[];
}) {
  const max = Math.max(1, ...rows.map((r) => Math.abs(r.value)));
  return (
    <div className="barlist">
      {rows.map((r) => (
        <div key={r.label} className="barlist-row">
          <div className="bl-label">{r.label}</div>
          <div className="bl-track">
            <div
              className={`bl-fill ${r.tone ?? ""}`}
              style={{ width: `${(Math.abs(r.value) / max) * 100}%` }}
            />
          </div>
          <div className="bl-value">{r.display}</div>
        </div>
      ))}
    </div>
  );
}

// Self-contained SVG time-series (no chart library). Plots one metric as an area+line across the
// replay window with event-onset markers. Width scales via viewBox; the y-scale is labelled.
function TimeSeries({
  points,
  markers,
  field,
  color,
  unit,
}: {
  points: TimelinePoint[];
  markers: { at: string; label: string }[];
  field: keyof TimelinePoint;
  color: string;
  unit: string;
}) {
  const W = 720;
  const H = 180;
  const padL = 34;
  const padR = 12;
  const padT = 12;
  const padB = 26;
  const n = points.length;
  const vals = points.map((p) => Number(p[field]));
  const maxV = Math.max(1, ...vals);
  const x = (i: number) => padL + (n <= 1 ? 0 : (i / (n - 1)) * (W - padL - padR));
  const y = (v: number) => padT + (1 - v / maxV) * (H - padT - padB);

  const line = points.map((p, i) => `${x(i)},${y(Number(p[field]))}`).join(" ");
  const area = `${padL},${y(0)} ${line} ${x(n - 1)},${y(0)}`;

  // Map an event's ISO time to the nearest x by matching the hour bucket.
  const markerX = (at: string): number => {
    const h = Number(at.slice(11, 13));
    let best = 0;
    let bestD = Infinity;
    points.forEach((p, i) => {
      const d = Math.abs(Number(p.cutoff.slice(11, 13)) - h);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    });
    return x(best);
  };

  return (
    <svg className="ts" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="이벤트 윈도우 시계열">
      {/* y grid: 0 and max */}
      {[0, maxV].map((gv) => (
        <g key={gv}>
          <line className="ts-grid" x1={padL} x2={W - padR} y1={y(gv)} y2={y(gv)} />
          <text className="ts-axis" x={padL - 6} y={y(gv) + 3} textAnchor="end">
            {gv}
          </text>
        </g>
      ))}
      {/* event onset markers */}
      {markers.map((m) => (
        <g key={m.at}>
          <line
            className="ts-marker"
            x1={markerX(m.at)}
            x2={markerX(m.at)}
            y1={padT}
            y2={H - padB}
          />
          <text className="ts-marker-label" x={markerX(m.at) + 3} y={padT + 9}>
            {m.label}
          </text>
        </g>
      ))}
      <polygon points={area} fill={color} fillOpacity={0.16} />
      <polyline points={line} fill="none" stroke={color} strokeWidth={2} />
      {points.map((p, i) => (
        <circle key={i} cx={x(i)} cy={y(Number(p[field]))} r={2.5} fill={color} />
      ))}
      {/* x ticks: hour labels */}
      {points.map((p, i) => (
        <text key={i} className="ts-axis" x={x(i)} y={H - 8} textAnchor="middle">
          {hourLabel(p.cutoff)}
        </text>
      ))}
      <text className="ts-unit" x={padL} y={H - 8} textAnchor="start" dx={-padL + 2}>
        {unit}
      </text>
    </svg>
  );
}

// Operator action: preview a live import of the real Citi Bike station network from GBFS.
function StationImport() {
  const [res, setRes] = useState<StationImportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    try {
      setRes(await api.importStations(60));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2>실제 정류장 네트워크 불러오기</h2>
          <div className="sub">
            무료·키 불필요 Citi Bike GBFS에서 실제 정류장(좌표·이름·용량)을 미리 불러옵니다.
            반영은 <span className="mono">make v2-import-stations</span>.
          </div>
        </div>
        <button className="btn primary" onClick={run} disabled={loading}>
          {loading ? "불러오는 중…" : "🛰 실제 정류장 미리보기"}
        </button>
      </div>
      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}
      {res?.status === "live" && (
        <div style={{ marginTop: 10 }}>
          <span className="badge live"><span className="dot" /> LIVE</span>{" "}
          <span className="muted small">실제 정류장 {res.count}개 로드</span>
          <div className="muted small" style={{ marginTop: 6 }}>
            {res.stations.slice(0, 6).map((s) => `${s.name}(${s.capacity})`).join(" · ")}
          </div>
        </div>
      )}
      {res?.status === "degraded" && (
        <div className="notice" style={{ marginTop: 10 }}>
          지금은 실제 정류장 데이터를 불러올 수 없어요(네트워크 연결 없음). 네트워크가 연결된 환경에서
          이용해 주세요.
        </div>
      )}
    </div>
  );
}

export default function StatisticsPage() {
  const { state, refreshKey } = useReplay();
  const cutoff = state?.cutoff ?? null;
  const stats = useApi<OperatorStatistics>(() => api.operatorStatistics(), [refreshKey]);
  const timeline = useApi<OperatorTimeline>(() => api.operatorTimeline(), [refreshKey]);

  if (stats.error) {
    return (
      <div className="notice error">
        API에 연결할 수 없습니다 ({stats.error}). <span className="mono">make api</span> 로 먼저 실행하세요.
      </div>
    );
  }
  if (stats.loading || !stats.data) return <div className="notice">통계를 집계하는 중…</div>;

  const d = stats.data;
  const utilPct = Math.round(d.system_utilization * 100);

  const eventTypeRows = Object.entries(d.events_by_type)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => ({ label: k, value: v, display: `${v}건` }));

  const surgeRows = d.zones
    .filter((z) => Math.abs(z.forecast_delta) > 0.001)
    .map((z) => ({
      label: z.ko,
      value: z.forecast_delta,
      display: `${signed(z.forecast_delta, 1)}/시간`,
      tone: z.forecast_delta > 0 ? "up" : "down",
    }));

  return (
    <div className="grid" style={{ gap: 18 }}>
      <div className="hero">
        <h1>운영 통계 · 분석</h1>
        <p className="muted">
          현재 재생 시각 기준으로 시스템 재고, 가용성 분포, 부족 부하, 이벤트 구성, 수요 변화(Δ) 분포를
          집계합니다. 상단 재생 시각을 바꾸면 모든 지표가 as-of로 다시 계산됩니다.
        </p>
      </div>

      <OpsCopilot cutoff={cutoff} />

      <StationImport />

      {/* KPI row */}
      <div className="grid cols-4">
        <Stat
          label="시스템 가동률"
          value={`${utilPct}%`}
          sub={`${d.total_bikes} / ${d.total_capacity}대`}
          tone={utilPct >= 80 || utilPct <= 20 ? "low" : "ok"}
        />
        <Stat
          label="총 대여 가능"
          value={`${d.total_bikes}대`}
          sub={`반납 여유 ${d.total_docks_free}칸`}
        />
        <Stat
          label="부족 대여소"
          value={`${d.stations_in_shortage}곳`}
          sub={`부족 ${d.total_shortage_units}대 · 여유 ${d.total_surplus_units}대`}
          tone={d.stations_in_shortage > 0 ? "low" : "ok"}
        />
        <Stat
          label="반영된 이벤트"
          value={`${d.available_event_count}건`}
          sub={`수요↑ ${d.events_by_effect.increase} · 수요↓ ${d.events_by_effect.decrease}`}
        />
      </div>

      {/* Event-window timeline — as-of aggregates across the replay window */}
      {timeline.data && timeline.data.points.length > 0 && (
        <div className="card">
          <h2>이벤트 윈도우 타임라인</h2>
          <div className="sub">
            재생 윈도우({hourLabel(timeline.data.window_start)}시–{hourLabel(timeline.data.window_end)}
            시) 동안 매 시각 as-of로 다시 계산한 부족 재고와 수요 변화(Δ). 세로 점선은 이벤트 공개
            시점입니다.
          </div>
          <div className="ts-grid-2">
            <div>
              <div className="ts-title">
                부족 재고 <span className="muted small">(units)</span>
              </div>
              <TimeSeries
                points={timeline.data.points}
                markers={timeline.data.event_markers.map((m) => ({
                  at: m.available_at,
                  label: m.demand_effect === "increase" ? "수요↑" : "이벤트",
                }))}
                field="total_shortage_units"
                color="var(--av-low)"
                unit="시"
              />
            </div>
            <div>
              <div className="ts-title">
                수요 변화 합계 Δ <span className="muted small">(/시간)</span>
              </div>
              <TimeSeries
                points={timeline.data.points}
                markers={timeline.data.event_markers.map((m) => ({
                  at: m.available_at,
                  label: m.demand_effect === "increase" ? "수요↑" : "이벤트",
                }))}
                field="demand_delta_total"
                color="var(--up)"
                unit="시"
              />
            </div>
          </div>
          <div className="ts-events">
            {timeline.data.event_markers.map((m) => (
              <span key={m.event_id} className="ts-event-chip">
                <span className="dot up" /> {hourLabel(m.available_at)}:
                {m.available_at.slice(14, 16)} · {m.event_title}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="grid cols-2">
        {/* Availability distribution */}
        <div className="card">
          <h2>가용성 분포</h2>
          <div className="sub">대여소 {d.station_count}곳의 재고 상태 분포</div>
          <StackBar counts={d.availability_counts} total={d.station_count} />
        </div>

        {/* Demand shift summary */}
        <div className="card">
          <h2>이벤트 수요 변화(Δ)</h2>
          <div className="sub">
            영향받은 지역 {d.affected_zone_count}곳 · 라벨: 데모 heuristic 예보 델타
          </div>
          <div className="grid cols-3" style={{ marginTop: 4 }}>
            <div>
              <div className="muted small">총 Δ</div>
              <div className="metric" style={{ fontSize: 24 }}>
                {signed(d.demand_delta_total, 1)}
              </div>
            </div>
            <div>
              <div className="muted small">최대 |Δ|</div>
              <div className="metric" style={{ fontSize: 24 }}>
                {d.demand_delta_max.toFixed(1)}
              </div>
            </div>
            <div>
              <div className="muted small">영향지역 평균 Δ</div>
              <div className="metric" style={{ fontSize: 24 }}>
                {signed(d.demand_delta_mean_affected, 1)}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid cols-2">
        {/* Event mix */}
        <div className="card">
          <h2>이벤트 유형 구성</h2>
          <div className="sub">현재 시각 기준 공개된 이벤트</div>
          {eventTypeRows.length > 0 ? (
            <BarList rows={eventTypeRows} />
          ) : (
            <div className="muted small">현재 시각 기준 공개된 이벤트가 없습니다.</div>
          )}
        </div>

        {/* Top surge zones */}
        <div className="card">
          <h2>수요 급증 지역</h2>
          <div className="sub">이벤트로 예상 수요가 오른 지역 (시간당 departures Δ)</div>
          {surgeRows.length > 0 ? (
            <BarList rows={surgeRows} />
          ) : (
            <div className="muted small">현재 수요가 급증한 지역이 없습니다.</div>
          )}
        </div>
      </div>

      {/* Per-zone table */}
      <div className="card">
        <h2>지역별 상세</h2>
        <div className="sub">
          기준 예보 → 이벤트 반영 예보, 재고, 가용성. 이벤트 노출(exposure)은 그래프 지표입니다.
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>지역</th>
                <th>구</th>
                <th>재고 / 정원</th>
                <th>가동률</th>
                <th>기준 예보</th>
                <th>이벤트 예보</th>
                <th>Δ</th>
                <th>상태</th>
              </tr>
            </thead>
            <tbody>
              {d.zones.map((z) => (
                <tr key={z.zone_id}>
                  <td>
                    <strong>{z.ko}</strong>
                    <div className="muted small">{z.en}</div>
                  </td>
                  <td className="muted">{z.area}</td>
                  <td>
                    {z.bikes} / {z.capacity}
                  </td>
                  <td>{Math.round(z.utilization * 100)}%</td>
                  <td>{z.baseline_forecast.toFixed(1)}</td>
                  <td>{z.event_aware_forecast.toFixed(1)}</td>
                  <td>
                    <span
                      className={`delta ${z.forecast_delta > 0.001 ? "up" : z.forecast_delta < -0.001 ? "down" : "flat"}`}
                    >
                      {signed(z.forecast_delta, 1)}
                    </span>
                  </td>
                  <td>
                    <span className={`status ${z.worst_level}`}>{LEVEL_LABEL[z.worst_level]}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <p className="muted small">{d.note}</p>
    </div>
  );
}

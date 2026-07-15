"use client";

import { useReplay } from "../providers";
import { useApi } from "@/lib/useApi";
import { api, type AvailabilityLevel, type OperatorStatistics } from "@/lib/api";
import { signed } from "@/lib/format";

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

export default function StatisticsPage() {
  const { refreshKey } = useReplay();
  const stats = useApi<OperatorStatistics>(() => api.operatorStatistics(), [refreshKey]);

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

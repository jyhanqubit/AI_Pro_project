"use client";

import { useRouter } from "next/navigation";
import { useReplay } from "./providers";
import { useApi } from "@/lib/useApi";
import {
  api,
  type EventOut,
  type ForecastsResponse,
  type RebalancingResponse,
  type StationStateOut,
} from "@/lib/api";
import { availability, freeDocks, signed, type Availability } from "@/lib/format";
import { stationPlace } from "@/lib/places";

// 자전거를 "빌리는 사람" 관점의 홈 화면.
// 어느 지역에 자전거가 넉넉할지 / 곧 부족할지를 한눈에 보여준다.
// 데이터는 오프라인 API의 재고(rebalancing.stations) + 수요 예보(forecasts) + 이벤트를 합친 것.

interface Row {
  s: StationStateOut;
  av: Availability;
  place: { ko: string; en: string; area: string };
  demandDelta: number; // 이벤트로 인한 예상 수요 증가(departures Δ), 없으면 0
  baseline: number | null;
  eventAware: number | null;
}

function Gauge({ bikes, capacity, level }: { bikes: number; capacity: number; level: string }) {
  const pct = capacity > 0 ? Math.min(100, Math.round((bikes / capacity) * 100)) : 0;
  return (
    <div className="gauge" aria-hidden="true">
      <div className={`gauge-fill ${level}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function StationCard({ row, onWhy }: { row: Row; onWhy: () => void }) {
  const { s, av, place } = row;
  const docks = freeDocks(s.bikes_before, s.capacity);
  const hasSurge = row.demandDelta > 0.001;
  return (
    <div className={`rider-card ${av.level}`}>
      <div className="rider-head">
        <div>
          <div className="rider-name">{place.ko}</div>
          <div className="rider-sub">
            {place.en} · {place.area}
          </div>
        </div>
        <span className={`status ${av.level}`}>{av.label}</span>
      </div>

      <div className="rider-bikes">
        <span className="big-num">{s.bikes_before}</span>
        <span className="unit">대</span>
        <span className="cap">/ 정원 {s.capacity}대</span>
      </div>
      <Gauge bikes={s.bikes_before} capacity={s.capacity} level={av.level} />

      <div className="rider-advice">{av.advice}</div>

      <div className="rider-meta">
        <div>
          <span className="k">반납 여유</span>
          <span className="v">{docks}칸</span>
        </div>
        {hasSurge ? (
          <div>
            <span className="k">예상 수요</span>
            <span className="v surge">
              {row.baseline?.toFixed(1)} → {row.eventAware?.toFixed(1)} /시간{" "}
              <span className="delta up">{signed(row.demandDelta, 1)}</span>
            </span>
          </div>
        ) : (
          <div>
            <span className="k">수요</span>
            <span className="v">평상시 수준</span>
          </div>
        )}
      </div>

      {hasSurge && (
        <button className="why-link" onClick={onWhy}>
          이 지역이 붐비는 이유 보기 →
        </button>
      )}
    </div>
  );
}

export default function RiderHome() {
  const router = useRouter();
  const { state, refreshKey, setSelectedZone } = useReplay();
  const cutoff = state?.cutoff ?? null;

  const reb = useApi<RebalancingResponse | null>(
    () => (cutoff ? api.rebalancing(cutoff, "greedy") : Promise.resolve(null)),
    [refreshKey, cutoff],
  );
  const fc = useApi<ForecastsResponse>(() => api.forecasts(), [refreshKey]);
  const ev = useApi<{ events: EventOut[] }>(() => api.events(), [refreshKey]);

  if (reb.error) {
    return (
      <div className="notice error">
        API에 연결할 수 없습니다 ({reb.error}). <span className="mono">make api</span> 로 먼저 실행하세요.
      </div>
    );
  }
  if (reb.loading || !reb.data) return <div className="notice">지역별 자전거 현황을 불러오는 중…</div>;

  const fcByZone = new Map((fc.data?.forecasts ?? []).map((f) => [f.zone_id, f]));
  const rows: Row[] = reb.data.stations
    .map((s) => {
      const f = fcByZone.get(s.zone_id) ?? null;
      return {
        s,
        av: availability(s.bikes_before, s.target, s.shortage_before),
        place: stationPlace(s.station_id),
        demandDelta: f?.forecast_delta ?? 0,
        baseline: f?.baseline_forecast ?? null,
        eventAware: f?.event_aware_forecast ?? null,
      };
    })
    .sort((a, b) => b.av.surplus - a.av.surplus);

  const good = rows.filter((r) => r.av.level === "plenty" || r.av.level === "ok");
  const low = rows.filter((r) => r.av.level === "low" || r.av.level === "tight");
  const events = ev.data?.events ?? [];
  const bestTwo = good.slice(0, 2).map((r) => r.place.ko);

  const goToWhy = (zoneId: string) => {
    setSelectedZone(zoneId);
    router.push("/why");
  };

  return (
    <div className="grid" style={{ gap: 20 }}>
      <div className="hero">
        <h1>지금 어디서 자전거를 빌릴까?</h1>
        <p className="muted">
          이벤트(교통장애·행사 등)를 반영해 지역별로 자전거가 얼마나 남아 있을지 예측합니다.
          여유가 많은 지역부터 보여드려요.
        </p>
      </div>

      <div className="grid cols-3">
        <div className="card stat">
          <div className="sub">빌리기 좋은 지역</div>
          <div className="metric ok-text">{good.length}곳</div>
          {bestTwo.length > 0 && <div className="muted small">추천: {bestTwo.join(", ")}</div>}
        </div>
        <div className="card stat">
          <div className="sub">곧 부족할 수 있는 지역</div>
          <div className="metric low-text">{low.length}곳</div>
          <div className="muted small">수요가 몰리는 곳은 서두르세요</div>
        </div>
        <div className="card stat">
          <div className="sub">반영된 이벤트</div>
          <div className="metric">{events.length}건</div>
          <div className="muted small">현재 시각 기준 공개된 사건만 반영</div>
        </div>
      </div>

      {low.length > 0 && bestTwo.length > 0 && (
        <div className="notice warn">
          수요가 몰리는 지역이 있어요. 자전거가 급하면 여유 지역(<strong>{bestTwo.join(", ")}</strong>)을
          이용하는 것을 추천합니다.
        </div>
      )}

      <div>
        <h2 className="section-title">지역별 자전거 현황</h2>
        <div className="rider-grid">
          {rows.map((r) => (
            <StationCard key={r.s.station_id} row={r} onWhy={() => goToWhy(r.s.zone_id)} />
          ))}
        </div>
      </div>

      {events.length > 0 && (
        <div className="card">
          <h2>지금 영향을 주는 이벤트</h2>
          <div className="sub">현재 재생 시각 기준으로 공개된 사건만 표시합니다.</div>
          <div className="grid" style={{ gap: 10 }}>
            {events.map((e) => (
              <div key={e.event_id} className="event-line">
                <span className={`pill ${e.demand_effect}`}>
                  {e.demand_effect === "increase" ? "수요 증가" : e.demand_effect === "decrease" ? "수요 감소" : "영향 불명"}
                </span>
                <div>
                  <strong>{e.event_title}</strong>
                  <div className="muted small">
                    {e.locations.map((l) => l.name).join(", ") || e.event_type}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

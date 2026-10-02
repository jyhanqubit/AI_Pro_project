"use client";

import { useApi } from "@/lib/useApi";
import { api, type LiveStation } from "@/lib/api";
import { fmtClock } from "@/lib/format";

// 라이브 재고 패널: Supabase에 매일 적재되는 Citi Bike GBFS 스냅숏의 최신분을 보여준다.
// 과거 재생(replay) 지표와 시각적으로 구분되도록 LIVE 배지와 스냅숏 시각을 항상 함께 표시하고,
// 연결이 없으면 degraded 안내만 보여준다(지어낸 숫자 없음).

function Row({ s, what }: { s: LiveStation; what: "bikes" | "docks" }) {
  const n = what === "bikes" ? s.bikes : s.docks;
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: "4px 0" }}>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {s.name ?? s.station_id}
        <span className="muted small"> · {regionLabel(s.region_id)}</span>
      </span>
      <span className="mono">
        {what === "bikes" ? "🚲" : "🅿️"} {n}
        <span className="muted small"> / {s.capacity ?? "?"}</span>
      </span>
    </div>
  );
}

function regionLabel(id: string | null): string {
  if (id === "70") return "저지시티";
  if (id === "311") return "호보켄";
  if (id === "71") return "뉴욕";
  return id ?? "";
}

function ageLabel(min: number | null): string {
  if (min === null) return "";
  if (min < 90) return `${Math.round(min)}분 전`;
  if (min < 48 * 60) return `${Math.round(min / 60)}시간 전`;
  return `${Math.round(min / 1440)}일 전`;
}

export function LiveInventory({ limit = 5 }: { limit?: number }) {
  const { data, error, loading } = useApi(() => api.liveInventory(limit), [limit]);

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0 }}>라이브 재고 (Citi Bike GBFS → Supabase)</h2>
          <div className="sub">매일 12:00 UTC에 DB가 직접 수집한 정류장 재고의 최신 스냅숏. 관측값이며 예측이 아닙니다.</div>
        </div>
        {data?.status === "live" && (
          <span className="badge live" title={`스냅숏 ${data.fetched_at}`}>
            <span className="dot" /> LIVE · {data.fetched_at ? fmtClock(data.fetched_at) : ""} ({ageLabel(data.age_minutes)})
          </span>
        )}
      </div>

      {loading && <p className="muted">불러오는 중…</p>}
      {error && <p className="pill decrease">API 오류: {error}</p>}

      {data?.status === "degraded" && (
        <div className="notice" style={{ marginTop: 10 }}>
          라이브 재고를 불러올 수 없습니다. {data.degraded_reason}
        </div>
      )}

      {data?.status === "live" && data.summary && (
        <>
          <div className="grid cols-3" style={{ marginTop: 12 }}>
            <div className="card stat">
              <h2>정류장</h2>
              <div className="metric mono">{data.summary.n_stations.toLocaleString()}</div>
              <div className="sub">운영 중지 {data.summary.not_renting}곳</div>
            </div>
            <div className="card stat">
              <h2>대여 가능 자전거</h2>
              <div className="metric mono">{data.summary.bikes_total.toLocaleString()}</div>
              <div className="sub">
                빈 정류장 {data.summary.empty_renting}곳 · 2대 이하 {data.summary.low_renting}곳
              </div>
            </div>
            <div className="card stat">
              <h2>빈 거치대</h2>
              <div className="metric mono">{data.summary.docks_total.toLocaleString()}</div>
              <div className="sub">꽉 찬 정류장 {data.summary.full_returning}곳</div>
            </div>
          </div>
          <div className="grid cols-2" style={{ marginTop: 12 }}>
            <div>
              <h3 style={{ margin: "0 0 6px" }}>자전거가 가장 적은 곳</h3>
              {data.lowest.map((s) => (
                <Row key={s.station_id} s={s} what="bikes" />
              ))}
            </div>
            <div>
              <h3 style={{ margin: "0 0 6px" }}>거치대가 가장 적은 곳</h3>
              {data.fullest.map((s) => (
                <Row key={s.station_id} s={s} what="docks" />
              ))}
            </div>
          </div>
          <div className="muted mono" style={{ fontSize: 11, marginTop: 10, wordBreak: "break-all" }}>
            출처: {data.source} · run: {data.run_id} · feed last_updated: {data.source_last_updated}
          </div>
        </>
      )}
    </div>
  );
}

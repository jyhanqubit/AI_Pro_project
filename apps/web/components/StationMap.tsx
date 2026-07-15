"use client";

import type { StationHit, AvailabilityLevel } from "@/lib/api";

// Offline station map. Instead of an external tile provider (which would need network + an API key
// and break Demo Mode), this projects each station's real lat/lng onto a self-contained SVG
// schematic. Markers are coloured by availability and open the same station detail sheet on click.
// It is clearly labelled a schematic (개략도) — it shows relative station positions, not streets.

const LEVEL_LABEL: Record<AvailabilityLevel, string> = {
  plenty: "넉넉",
  ok: "여유",
  tight: "빠듯",
  low: "곧 부족",
};

const W = 640;
const H = 460;
const PAD = 56;

interface Props {
  stations: StationHit[];
  onOpen: (stationId: string) => void;
}

export function StationMap({ stations, onOpen }: Props) {
  if (stations.length === 0) {
    return <div className="notice">표시할 대여소가 없어요.</div>;
  }

  const lats = stations.map((s) => s.lat);
  const lngs = stations.map((s) => s.lng);
  const latMin = Math.min(...lats);
  const latMax = Math.max(...lats);
  const lngMin = Math.min(...lngs);
  const lngMax = Math.max(...lngs);
  const meanLat = (latMin + latMax) / 2;
  const kx = Math.cos((meanLat * Math.PI) / 180); // longitude compression at this latitude

  // Geographic extent in degree-equivalent units (guard against a zero span).
  const gw = Math.max((lngMax - lngMin) * kx, 1e-9);
  const gh = Math.max(latMax - latMin, 1e-9);
  const innerW = W - 2 * PAD;
  const innerH = H - 2 * PAD;
  const scale = Math.min(innerW / gw, innerH / gh);
  const offX = (innerW - gw * scale) / 2;
  const offY = (innerH - gh * scale) / 2;

  const project = (lat: number, lng: number): [number, number] => {
    const gx = (lng - lngMin) * kx;
    const gy = latMax - lat; // invert: north (higher lat) is up
    return [PAD + offX + gx * scale, PAD + offY + gy * scale];
  };

  // Draw the busiest (곧 부족) markers last so they sit on top.
  const order: Record<AvailabilityLevel, number> = { plenty: 0, ok: 1, tight: 2, low: 3 };
  const sorted = [...stations].sort((a, b) => order[a.level] - order[b.level]);

  return (
    <div className="map-wrap">
      <svg
        className="station-map"
        viewBox={`0 0 ${W} ${H}`}
        role="group"
        aria-label="대여소 위치 개략도"
      >
        {/* faint reference grid */}
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={`v${f}`} className="map-grid" x1={W * f} y1={0} x2={W * f} y2={H} />
        ))}
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={`h${f}`} className="map-grid" x1={0} y1={H * f} x2={W} y2={H * f} />
        ))}
        <text className="map-caption" x={16} y={H - 16}>
          저지시티 · 호보켄 일대 개략도 (실제 위·경도 기준, 도로는 표시하지 않음)
        </text>
        <text className="map-compass" x={W - 22} y={30}>
          N ↑
        </text>

        {sorted.map((s) => {
          const [x, y] = project(s.lat, s.lng);
          const surge = s.demand_delta > 0.001;
          return (
            <g
              key={s.station_id}
              className="map-marker"
              role="button"
              tabIndex={0}
              aria-label={`${s.ko} — 자전거 ${s.bikes}대, ${LEVEL_LABEL[s.level]}`}
              onClick={() => onOpen(s.station_id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onOpen(s.station_id);
                }
              }}
            >
              {surge && <circle className="map-pulse" cx={x} cy={y} r={22} />}
              <circle className={`map-dot ${s.level}`} cx={x} cy={y} r={16} />
              <text className="map-count" x={x} y={y + 5} textAnchor="middle">
                {s.bikes}
              </text>
              <g transform={`translate(${x}, ${y + 30})`}>
                <text className="map-label" textAnchor="middle">
                  {surge ? "🔥 " : ""}
                  {s.ko}
                </text>
              </g>
            </g>
          );
        })}
      </svg>

      <div className="map-legend">
        {(["plenty", "ok", "tight", "low"] as AvailabilityLevel[]).map((lv) => (
          <span key={lv} className="legend-item">
            <span className={`dot ${lv}`} /> {LEVEL_LABEL[lv]}
          </span>
        ))}
        <span className="legend-item muted">🔥 이벤트로 수요 급증</span>
      </div>
    </div>
  );
}

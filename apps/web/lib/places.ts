// Human-readable place names for the demo zones/stations.
//
// The forecast grain is an H3 zone (an opaque code like `892a1072e7bffff`), and the
// station fixture uses ids like `JC_GROVE`. Neither is meaningful to a rider, so this
// module maps both to real Jersey City / Hoboken neighbourhood names (Korean + English).
// Coordinates mirror config/places.py and data/fixtures/rebalancing_demo.json so the two
// stay in sync with the backend gazetteer.

export interface Place {
  ko: string; // Korean neighbourhood name shown to riders
  en: string; // official English station name (matches the fixture)
  area: string; // borough / district, for grouping
}

const ZONE_TO_PLACE: Record<string, Place> = {
  "892a1072e7bffff": { ko: "그로브 스트리트", en: "Grove St PATH", area: "저지시티" },
  "892a1072e3bffff": { ko: "익스체인지 플레이스", en: "Exchange Place", area: "저지시티" },
  "892a107216bffff": { ko: "호보켄 터미널", en: "Hoboken Terminal", area: "호보켄" },
  "892a10723b7ffff": { ko: "저지시티 시청", en: "City Hall", area: "저지시티" },
  "892a1072ec7ffff": { ko: "뉴포트", en: "Newport", area: "저지시티" },
};

const STATION_TO_PLACE: Record<string, Place> = {
  JC_GROVE: ZONE_TO_PLACE["892a1072e7bffff"],
  JC_EXCHANGE: ZONE_TO_PLACE["892a1072e3bffff"],
  JC_HOBOKEN: ZONE_TO_PLACE["892a107216bffff"],
  JC_CITYHALL: ZONE_TO_PLACE["892a10723b7ffff"],
  JC_NEWPORT: ZONE_TO_PLACE["892a1072ec7ffff"],
};

function shortCode(code: string): string {
  return code ? `…${code.slice(-6)}` : "—";
}

/** Place for a zone code, or a graceful fallback carrying the short code. */
export function zonePlace(zoneId: string): Place {
  return (
    ZONE_TO_PLACE[zoneId] ?? { ko: shortCode(zoneId), en: shortCode(zoneId), area: "" }
  );
}

/** Place for a station id (falls back to the id itself). */
export function stationPlace(stationId: string): Place {
  return STATION_TO_PLACE[stationId] ?? { ko: stationId, en: stationId, area: "" };
}

/** Rider-facing label: "그로브 스트리트 (Grove St PATH)". */
export function zoneLabel(zoneId: string): string {
  const p = zonePlace(zoneId);
  return p.ko === p.en ? p.ko : `${p.ko} (${p.en})`;
}

/** Short Korean-only name for tight spaces. */
export function zoneNameKo(zoneId: string): string {
  return zonePlace(zoneId).ko;
}

export function stationLabel(stationId: string): string {
  const p = stationPlace(stationId);
  return p.ko === p.en ? p.ko : `${p.ko} (${p.en})`;
}

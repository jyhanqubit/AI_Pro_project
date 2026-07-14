// Small formatting helpers for the rider / operator UI. Locale is Korean.

export function fmtClock(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("ko-KR", {
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function deltaClass(delta: number): "up" | "down" | "flat" {
  if (delta > 0.001) return "up";
  if (delta < -0.001) return "down";
  return "flat";
}

export function signed(n: number, digits = 2): string {
  const v = n.toFixed(digits);
  return n > 0 ? `+${v}` : v;
}

// Map the API cutoff (ISO with -04:00) to a slider position within the demo window.
export function hourFromIso(iso: string): number {
  return new Date(iso).getHours();
}

// ---- Rider availability model (transparent demo heuristic) --------------------
//
// The backend gives, per station: current bikes, capacity, and a demand-adjusted
// `target` (the desired inventory this hour; raised in event-exposed zones by the
// demo-heuristic forecast). From a rider's point of view:
//   surplus = bikes - target  →  how many bikes are available beyond expected demand.
// A positive surplus means "plenty to rent"; a negative one means the zone is draining.

export type AvailabilityLevel = "plenty" | "ok" | "tight" | "low";

export interface Availability {
  level: AvailabilityLevel;
  label: string; // Korean status label
  advice: string; // one-line rider advice
  surplus: number; // bikes - target
}

export function availability(
  bikes: number,
  target: number,
  shortage: number,
): Availability {
  const surplus = bikes - target;
  if (shortage > 0) {
    return {
      level: "low",
      label: "곧 부족",
      advice: "수요가 몰려요 — 서두르거나 여유 지역을 이용하세요.",
      surplus,
    };
  }
  if (surplus >= 6) {
    return {
      level: "plenty",
      label: "넉넉",
      advice: "자전거가 많아요 — 지금 빌리기 좋아요.",
      surplus,
    };
  }
  if (surplus >= 2) {
    return {
      level: "ok",
      label: "여유",
      advice: "빌릴 수 있어요.",
      surplus,
    };
  }
  return {
    level: "tight",
    label: "빠듯",
    advice: "재고가 빠듯해요 — 서두르는 게 좋아요.",
    surplus,
  };
}

/** Free docks for returning a bike. */
export function freeDocks(bikes: number, capacity: number): number {
  return Math.max(0, capacity - bikes);
}

// Small formatting helpers for the operator UI.

export function fmtClock(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-US", {
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

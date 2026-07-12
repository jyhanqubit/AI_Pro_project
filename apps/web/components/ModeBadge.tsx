import type { OperatingMode } from "@/lib/api";

const LABELS: Record<OperatingMode, string> = {
  demo_fixture: "Demo Fixture",
  historical_replay: "Historical Replay",
  live: "Live",
  research: "Research",
};

// Historical Replay and Live must be visually distinct (section 13).
export function ModeBadge({ mode }: { mode: OperatingMode }) {
  const cls = mode === "live" ? "live" : "replay";
  return (
    <span className={`badge ${cls}`} title={`Operating mode: ${LABELS[mode]}`}>
      <span className="dot" />
      {LABELS[mode]}
    </span>
  );
}

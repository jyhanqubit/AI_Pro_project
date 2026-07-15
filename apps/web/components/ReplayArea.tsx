"use client";

import { useRole } from "@/app/role";
import { ReplayControl } from "./ReplayControl";
import { RiderClock } from "./RiderClock";

// Role-aware replay strip: operators get the full replay clock (scrubber + event presets);
// riders get a compact read-only indicator.
export function ReplayArea() {
  const { role } = useRole();
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      {role === "operator" ? <ReplayControl /> : <RiderClock />}
    </div>
  );
}

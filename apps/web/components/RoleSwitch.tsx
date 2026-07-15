"use client";

import { useRouter } from "next/navigation";
import { useRole, type Role } from "@/app/role";

// Top-level segmented control: switch between the rider and operator experiences.
export function RoleSwitch() {
  const { role, setRole } = useRole();
  const router = useRouter();

  const pick = (r: Role) => {
    setRole(r);
    router.push(r === "rider" ? "/" : "/statistics"); // each role's landing screen
  };

  return (
    <div className="role-switch" role="tablist" aria-label="역할 선택">
      <button
        role="tab"
        aria-selected={role === "rider"}
        className={role === "rider" ? "active" : ""}
        onClick={() => pick("rider")}
      >
        🚲 라이더
      </button>
      <button
        role="tab"
        aria-selected={role === "operator"}
        className={role === "operator" ? "active" : ""}
        onClick={() => pick("operator")}
      >
        🛠 운영자
      </button>
    </div>
  );
}

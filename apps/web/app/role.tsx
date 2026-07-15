"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";

// Top-level experience split (V2): the rider sees a clean consumer app; the operator sees the
// analysis tools. Role is an explicit, persisted choice — not a security boundary (Demo Mode).

export type Role = "rider" | "operator";

// Operator-only tools. Landing on one of these deep-links straight into the operator experience.
// `/why` is intentionally excluded: the rider station sheet links to it ("why is this busy?"), so
// it must stay reachable in rider mode.
const OPERATOR_ONLY = new Set([
  "/statistics",
  "/news",
  "/scenario",
  "/rebalancing",
  "/model-lift",
  "/anomaly",
  "/experiment",
]);

interface RoleContextValue {
  role: Role;
  setRole: (r: Role) => void;
}

const RoleContext = createContext<RoleContextValue | null>(null);
const STORAGE_KEY = "shockflow.role";

export function RoleProvider({ children }: { children: ReactNode }) {
  const path = usePathname();
  const [role, setRoleState] = useState<Role>("rider");

  // Hydrate the persisted role after mount (avoids SSR/client mismatch).
  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "rider" || saved === "operator") setRoleState(saved);
  }, []);

  // A deep link into an operator-only tool implies the operator experience.
  useEffect(() => {
    if (OPERATOR_ONLY.has(path)) {
      setRoleState("operator");
      window.localStorage.setItem(STORAGE_KEY, "operator");
    }
  }, [path]);

  const setRole = (r: Role) => {
    setRoleState(r);
    window.localStorage.setItem(STORAGE_KEY, r);
  };

  return <RoleContext.Provider value={{ role, setRole }}>{children}</RoleContext.Provider>;
}

export function useRole(): RoleContextValue {
  const ctx = useContext(RoleContext);
  if (!ctx) throw new Error("useRole must be used within RoleProvider");
  return ctx;
}

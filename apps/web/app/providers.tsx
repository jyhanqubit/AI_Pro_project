"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api, type ReplayState } from "@/lib/api";

interface ReplayContextValue {
  state: ReplayState | null;
  error: string | null;
  refreshKey: number;
  selectedZone: string | null;
  setSelectedZone: (zone: string) => void;
  setCutoff: (iso: string) => Promise<void>;
  refresh: () => void;
}

const ReplayContext = createContext<ReplayContextValue | null>(null);

export function ReplayProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ReplayState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedZone, setSelectedZone] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setState(await api.replayState());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const setCutoff = useCallback(async (iso: string) => {
    try {
      const next = await api.setCutoff(iso);
      setState(next);
      setError(null);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  return (
    <ReplayContext.Provider
      value={{ state, error, refreshKey, selectedZone, setSelectedZone, setCutoff, refresh }}
    >
      {children}
    </ReplayContext.Provider>
  );
}

export function useReplay(): ReplayContextValue {
  const ctx = useContext(ReplayContext);
  if (!ctx) throw new Error("useReplay must be used within ReplayProvider");
  return ctx;
}

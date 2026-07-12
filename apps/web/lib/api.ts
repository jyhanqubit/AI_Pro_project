// Typed client for the ShockFlow API (section 12). Mirrors services/api/schemas.py.
// All calls are read-only or idempotent; Demo Mode runs offline against `make api`.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export type OperatingMode =
  | "demo_fixture"
  | "historical_replay"
  | "live"
  | "research";

export type EffectDirection = "increase" | "decrease" | "unknown";

export interface ReplayState {
  mode: OperatingMode;
  cutoff: string;
  window_start: string;
  window_end: string;
  available_event_count: number;
}

export interface EvidenceOut {
  article_id: string;
  text: string;
}

export interface LocationOut {
  name: string;
  lat: number | null;
  lng: number | null;
}

export interface EventOut {
  event_id: string;
  event_type: string;
  event_title: string;
  event_summary: string;
  available_at: string | null;
  event_start_at: string | null;
  demand_effect: EffectDirection;
  severity: number;
  confidence: number;
  locations: LocationOut[];
  source_article_ids: string[];
  evidence_spans: EvidenceOut[];
}

export interface ForecastOut {
  zone_id: string;
  forecast_cutoff: string;
  forecast_horizon: number;
  model_version: string;
  feature_version: string;
  target_name: string;
  baseline_forecast: number;
  event_aware_forecast: number;
  forecast_delta: number;
  event_exposure: number;
  mode: OperatingMode;
}

export interface ForecastsResponse {
  mode: OperatingMode;
  cutoff: string;
  model_version: string;
  feature_version: string;
  target_name: string;
  forecasts: ForecastOut[];
}

export interface TraceStep {
  event_id: string;
  event_type: string;
  event_title: string;
  demand_effect: EffectDirection;
  severity: number;
  confidence: number;
  source_article_ids: string[];
  evidence_spans: EvidenceOut[];
  contributed_features: Record<string, number>;
}

export interface ExplanationResponse {
  mode: OperatingMode;
  zone_id: string;
  cutoff: string;
  model_version: string;
  feature_version: string;
  baseline_forecast: number;
  event_aware_forecast: number;
  forecast_delta: number;
  event_exposure: number;
  drivers: TraceStep[];
  note: string;
}

export interface ScenarioZone {
  zone_id: string;
  baseline_forecast: number;
  scenario_forecast: number;
  default_event_aware_forecast: number;
  scenario_delta: number;
}

export interface ScenarioResponse {
  mode: OperatingMode;
  cutoff: string;
  disabled_event_ids: string[];
  model_version: string;
  feature_version: string;
  zones: ScenarioZone[];
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail?.message ?? JSON.stringify(body);
    } catch {
      /* keep statusText */
    }
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => req<{ status: string; mode: OperatingMode }>("/v1/health"),
  replayState: () => req<ReplayState>("/v1/replay/state"),
  setCutoff: (cutoff: string) =>
    req<ReplayState>("/v1/replay/set-cutoff", {
      method: "POST",
      body: JSON.stringify({ cutoff }),
    }),
  events: () => req<{ mode: OperatingMode; cutoff: string; events: EventOut[] }>("/v1/events"),
  forecasts: () => req<ForecastsResponse>("/v1/forecasts"),
  explanation: (zoneId: string) =>
    req<ExplanationResponse>(`/v1/zones/${encodeURIComponent(zoneId)}/explanation`),
  scenario: (cutoff: string, disabled: string[]) =>
    req<ScenarioResponse>("/v1/scenarios", {
      method: "POST",
      body: JSON.stringify({ cutoff, disabled_event_ids: disabled }),
    }),
};

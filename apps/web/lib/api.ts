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

export interface MoveOut {
  origin_station_id: string;
  destination_station_id: string;
  quantity: number;
  distance_km: number;
}

export interface StationStateOut {
  station_id: string;
  name: string;
  zone_id: string;
  bikes_before: number;
  bikes_after: number;
  target: number;
  base_target: number;
  capacity: number;
  shortage_before: number;
  shortage_after: number;
}

export interface RebalancingResponse {
  mode: OperatingMode;
  cutoff: string;
  model_version: string;
  method: string;
  feasible: boolean;
  infeasibility_reason: string | null;
  vehicle_capacity: number;
  total_moved: number;
  total_distance_km: number;
  shortage_units_before: number;
  shortage_units_after: number;
  overflow_units_before: number;
  overflow_units_after: number;
  shortage_reduction: number;
  overflow_reduction: number;
  total_cost: number;
  baseline_cost: number;
  moves: MoveOut[];
  stations: StationStateOut[];
  note: string;
}

export interface ExperimentArm {
  policy: string;
  label: string;
  description: string;
}

export interface ExperimentOut {
  experiment_id: string;
  hypothesis: string;
  arm_a: ExperimentArm;
  arm_b: ExperimentArm;
  n_units: number;
  itt_effect: number;
  itt_ci: [number, number];
  cuped_itt_effect: number;
  cuped_ci: [number, number];
  srm_ok: boolean;
  ci_excludes_zero: boolean;
  status: string;
}

export interface ExperimentsResponse {
  design: string;
  randomization_unit: string;
  metric_name: string;
  is_simulated: boolean;
  disclaimer: string;
  aa_validation_passed: boolean;
  experiments: ExperimentOut[];
}

export interface AblationArm {
  arm: string;
  label: string;
  wape: number;
  mae: number;
  mase: number;
}

export interface ModelLiftResponse {
  model_version: string;
  feature_version: string;
  target: string;
  n_test: number | null;
  ablation: AblationArm[];
  m0_baseline: { wape: number; mae: number; mase: number };
  m1_event_aware: { wape: number; mae: number; mase: number };
  model_attributed_wape_lift: number;
  event_lift_verdict: string;
  event_verification: Record<string, unknown>;
  note: string;
}

export interface NewsHit {
  article_id: string;
  title: string;
  source: string;
  published_at: string;
  score: number;
}
export interface NewsSearchResponse {
  query: string;
  n_indexed: number;
  embedder: string;
  results: NewsHit[];
}
export interface NewsCluster {
  cluster_id: number;
  size: number;
  representative_title: string;
  article_ids: string[];
}
export interface NewsClustersResponse {
  n_indexed: number;
  threshold: number;
  n_clusters: number;
  clusters: NewsCluster[];
}

export interface AnomalyAlertOut {
  anomaly_id: string;
  detector: string;
  anomaly_type: string;
  station_id: string;
  zone_id: string;
  detected_at: string;
  score: number;
  severity: number;
  root_cause_status: string;
  linked_event_ids: string[];
  evidence_article_ids: string[];
  is_synthetic_fault: boolean;
}
export interface AnomaliesResponse {
  mode: string;
  n_alerts: number;
  synthetic_fault_count: number;
  by_type: Record<string, number>;
  by_root_cause: Record<string, number>;
  note: string;
  alerts: AnomalyAlertOut[];
}

// ---- V2: rider station search + operator statistics -------------------------
export type AvailabilityLevel = "plenty" | "ok" | "tight" | "low";

export interface StationHit {
  station_id: string;
  ko: string;
  en: string;
  area: string;
  zone_id: string;
  bikes: number;
  capacity: number;
  docks_free: number;
  target: number;
  base_target: number;
  shortage: number;
  surplus: number;
  level: AvailabilityLevel;
  level_label: string;
  lat: number;
  lng: number;
  demand_delta: number;
  baseline_forecast: number;
  event_aware_forecast: number;
}

export interface StationSearchResponse {
  mode: OperatingMode;
  cutoff: string;
  query: string;
  count: number;
  stations: StationHit[];
}

export interface ZoneStat {
  zone_id: string;
  ko: string;
  en: string;
  area: string;
  station_count: number;
  bikes: number;
  capacity: number;
  utilization: number;
  baseline_forecast: number;
  event_aware_forecast: number;
  forecast_delta: number;
  event_exposure: number;
  worst_level: AvailabilityLevel;
  shortage: number;
}

export interface OperatorStatistics {
  mode: OperatingMode;
  cutoff: string;
  model_version: string;
  feature_version: string;
  note: string;
  station_count: number;
  total_bikes: number;
  total_capacity: number;
  total_docks_free: number;
  system_utilization: number;
  availability_counts: Record<AvailabilityLevel, number>;
  stations_in_shortage: number;
  total_shortage_units: number;
  total_surplus_units: number;
  available_event_count: number;
  events_by_effect: Record<EffectDirection, number>;
  events_by_type: Record<string, number>;
  affected_zone_count: number;
  demand_delta_total: number;
  demand_delta_max: number;
  demand_delta_mean_affected: number;
  zones: ZoneStat[];
  top_surge_zones: ZoneStat[];
}

export interface TimelinePoint {
  cutoff: string;
  event_count: number;
  affected_zone_count: number;
  total_shortage_units: number;
  stations_in_shortage: number;
  demand_delta_total: number;
  demand_delta_max: number;
}

export interface TimelineMarker {
  event_id: string;
  event_type: string;
  event_title: string;
  available_at: string;
  demand_effect: EffectDirection;
}

export interface OperatorTimeline {
  mode: OperatingMode;
  model_version: string;
  feature_version: string;
  window_start: string;
  window_end: string;
  step_hours: number;
  note: string;
  points: TimelinePoint[];
  event_markers: TimelineMarker[];
}

export interface AllocationStation {
  station_id: string;
  ko: string;
  en: string;
  area: string;
  zone_id: string;
  bikes_before: number;
  added: number;
  bikes_after: number;
  target: number;
  base_target: number;
  capacity: number;
  shortage_before: number;
  shortage_after: number;
}

export interface AllocationResponse {
  mode: OperatingMode;
  cutoff: string;
  model_version: string;
  feature_version: string;
  method: string;
  extra_requested: number;
  placed: number;
  leftover: number;
  shortage_units_before: number;
  shortage_units_after: number;
  overflow_units_before: number;
  overflow_units_after: number;
  cost_before: number;
  cost_after: number;
  benefit: number;
  shortage_reduction: number;
  stations: AllocationStation[];
  note: string;
}

export interface CopilotEvent {
  event_id: string;
  event_type: string;
  event_title: string;
  demand_effect: EffectDirection;
}

export interface RiderAskResponse {
  mode: OperatingMode;
  cutoff: string;
  model_version: string;
  query: string;
  intent: string;
  supported: boolean;
  answer: string;
  stations: StationHit[];
  events: CopilotEvent[];
  note: string;
}

export interface PriceQuote {
  station_id: string;
  ko: string;
  en: string;
  zone_id: string;
  level: AvailabilityLevel;
  level_label: string;
  bikes: number;
  target: number;
  capacity: number;
  demand_delta: number;
  scarcity_score: number;
  components: {
    shortage_probability: number;
    normalized_gap: number;
    event_impact: number;
    neighbor_buffer: number;
  };
  base_fare: number;
  tier_multiplier: number;
  scarcity_surcharge: number;
  final_price: number;
  balancing_credit: number;
  tier_reason: string;
  guardrails: { stale: boolean; safety_block: boolean; capped: boolean };
  quote_id: string;
}

export interface PricingResponse {
  mode: OperatingMode;
  cutoff: string;
  model_version: string;
  pricing_config_version: string;
  is_simulated: boolean;
  shadow: boolean;
  disclaimer: string;
  scenario: { stale: boolean; safety: boolean };
  base_fare: number;
  tiers: number[];
  quotes: PriceQuote[];
  note: string;
}

export interface OpsAskResponse {
  mode: OperatingMode;
  cutoff: string;
  model_version: string;
  query: string;
  intent: string;
  supported: boolean;
  answer: string;
  facts: Record<string, unknown>;
  link: { label: string; href: string } | null;
  note: string;
  // V2-08 GraphRAG: "graphrag_llm" when a GPT/Claude key is configured, else "rule_based".
  answer_mode?: "graphrag_llm" | "rule_based";
  llm_provider?: string;
  citations?: { event_id: string; title: string }[];
  grounded_event_count?: number;
}

export interface PredictiveLiftResponse {
  protocol: string;
  coverage: {
    unique_events: number;
    unique_sources: number;
    event_types: number;
    affected_zone_hours: number;
  };
  coverage_gate: Record<string, number>;
  coverage_conditions: Record<string, boolean>;
  coverage_ok: boolean;
  verdict: string;
  claim_enabled: boolean;
  mean_gain: number;
  ci_95: [number, number];
  note: string;
}

export interface NewsSyncArticle {
  article_id: string;
  title: string;
  source: string;
  published_at: string;
  url: string;
}

export interface NewsSyncResponse {
  status: "live" | "degraded";
  mode: string;
  query: string;
  fetched_at: string;
  fetched: number;
  added_to_index: number;
  unique_sources: number;
  sources?: string[];
  articles: NewsSyncArticle[];
  degraded_reason?: string;
  note: string;
}

export interface StationImportResponse {
  status: "live" | "degraded";
  mode: string;
  source: string;
  fetched_at: string;
  count: number;
  stations: { station_id: string; name: string; lat: number; lng: number; capacity: number }[];
  degraded_reason?: string;
  note: string;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch (e) {
    // Surface the exact URL the browser tried, so a deploy issue is diagnosable at a glance
    // (localhost = NEXT_PUBLIC_API_BASE not built in; onrender = reachable but CORS-blocked).
    const msg = e instanceof Error ? e.message : String(e);
    throw new Error(`요청 실패 → ${url} (${msg})`);
  }
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

export interface RevenueResponse {
  mode: OperatingMode;
  cutoff: string;
  is_simulated: boolean;
  shadow: boolean;
  disclaimer: string;
  elasticity: number;
  base_fare: number;
  max_multiplier: number;
  disabled_event_ids: string[];
  demand: {
    baseline_total: number;
    event_aware_total: number;
    delta: number;
    delta_pct: number;
    affected_zones: number;
    n_stations: number;
  };
  pricing: {
    surcharged_stations: number;
    max_multiplier: number;
    base_fare: number;
    cap: number;
  };
  revenue: {
    flat_revenue: number;
    flat_fulfilled: number;
    dynamic_revenue: number;
    dynamic_fulfilled: number;
    revenue_uplift: number;
    revenue_uplift_pct: number;
    fulfilled_delta: number;
  };
  stations: {
    station_id: string;
    zone_id: string;
    multiplier: number;
    final_price: number;
    would_be_renters: number;
    available_bikes: number;
    fulfilled_rentals: number;
    revenue: number;
    tier_reason: string;
  }[];
  note: string;
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
  rebalancing: (cutoff: string, method: "greedy" | "milp" = "milp") =>
    req<RebalancingResponse>("/v1/rebalancing/solve", {
      method: "POST",
      body: JSON.stringify({ cutoff, method }),
    }),
  experiments: () => req<ExperimentsResponse>("/v1/experiments/switchback"),
  modelLift: () => req<ModelLiftResponse>("/v1/model/lift"),
  predictiveLift: () => req<PredictiveLiftResponse>("/v2/model/predictive-lift"),
  newsSync: (query?: string) =>
    req<NewsSyncResponse>("/v2/news/sync", {
      method: "POST",
      body: JSON.stringify(query ? { query } : {}),
    }),
  newsSearch: (q: string, k = 5) =>
    req<NewsSearchResponse>(`/v1/news/search?q=${encodeURIComponent(q)}&k=${k}`),
  newsClusters: (threshold = 0.3) =>
    req<NewsClustersResponse>(`/v1/news/clusters?threshold=${threshold}`),
  anomalies: () => req<AnomaliesResponse>("/v1/anomalies"),
  stationSearch: (q = "", k = 20) =>
    req<StationSearchResponse>(
      `/v2/rider/stations/search?q=${encodeURIComponent(q)}&k=${k}`,
    ),
  operatorStatistics: () => req<OperatorStatistics>("/v2/operator/statistics"),
  operatorTimeline: () => req<OperatorTimeline>("/v2/operator/timeline"),
  importStations: (limit = 60) =>
    req<StationImportResponse>(`/v2/operator/stations/import?limit=${limit}`, {
      method: "POST",
    }),
  opsAsk: (query: string, cutoff?: string) =>
    req<OpsAskResponse>("/v2/operator/ask", {
      method: "POST",
      body: JSON.stringify({ query, cutoff: cutoff ?? null }),
    }),
  riderAsk: (query: string, cutoff?: string) =>
    req<RiderAskResponse>("/v2/rider/ask", {
      method: "POST",
      body: JSON.stringify({ query, cutoff: cutoff ?? null }),
    }),
  pricingQuote: (opts?: { stale?: boolean; safety?: boolean; cutoff?: string }) =>
    req<PricingResponse>("/v2/pricing/quote", {
      method: "POST",
      body: JSON.stringify({
        stale: opts?.stale ?? false,
        safety: opts?.safety ?? false,
        cutoff: opts?.cutoff ?? null,
      }),
    }),
  revenue: (cutoff: string, disabled: string[], elasticity = 0.5) =>
    req<RevenueResponse>("/v2/pricing/revenue", {
      method: "POST",
      body: JSON.stringify({
        cutoff,
        disabled_event_ids: disabled,
        elasticity,
      }),
    }),
  allocateExtraBikes: (extraBikes: number, cutoff?: string) =>
    req<AllocationResponse>("/v2/operator/rebalancing/allocate", {
      method: "POST",
      body: JSON.stringify({ extra_bikes: extraBikes, cutoff: cutoff ?? null }),
    }),
};

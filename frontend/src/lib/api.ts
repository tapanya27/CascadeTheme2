/**
 * Typed API client. Base URL comes from NEXT_PUBLIC_API_BASE_URL — never hardcoded.
 */

import type {
  DependencyGraph,
  GeoJsonFeatureCollection,
  InterventionListResponse,
  InterventionScenario,
  LatestAssessmentsResponse,
  MapLayersResponse,
  OverviewResponse,
  RunAssessmentsResponse,
  SensitivityResponse,
  ZoneContextResponse,
  ZoneExplanation,
} from "@/lib/types";

export type HealthResponse = {
  status: string;
  version: string;
  database: string;
  postgis: boolean;
  postgis_version: string | null;
  error: string | null;
};

export type MetadataResponse = {
  project: string;
  module: string;
  study_area: string;
  spatial_srid: number;
  database_required: string;
  endpoints: string[];
  notes: string[];
};

export type ZoneOut = {
  id: string;
  city_id: string;
  code: string;
  name: string;
  description: string | null;
  properties: Record<string, unknown>;
  data_source_id: string;
  data_source_name: string | null;
  is_synthetic: boolean | null;
  geojson: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  latest_score?: number | null;
  latest_category?: string | null;
  latest_confidence?: number | null;
  latest_assessment_id?: string | null;
  hazard_only_score?: number | null;
  hazard_only_rank?: number | null;
  multifactor_rank?: number | null;
  rank_uplift?: number | null;
};

export type {
  Assessment,
  ComponentScore,
  DataQuality,
  DependencyGraph,
  GraphEdge,
  GraphNode,
  InterventionListResponse,
  InterventionScenario,
  LatestAssessmentsResponse,
  MapLayersResponse,
  OverviewResponse,
  RunAssessmentsResponse,
  SensitivityResponse,
  ZoneContextResponse,
  ZoneExplanation,
} from "@/lib/types";

export type ZoneListResponse = {
  items: ZoneOut[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

export type DataSourceOut = {
  id: string;
  city_id: string;
  name: string;
  kind: string;
  is_synthetic: boolean;
  description: string | null;
  provider: string | null;
  retrieval_url: string | null;
  license_note: string | null;
  retrieved_at: string | null;
  provenance: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

function withCity(path: string, cityId: string): string {
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}city_id=${encodeURIComponent(cityId)}`;
}

export type ValidationResult = {
  valid: boolean;
  record_type: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  issues: { row?: number; field?: string; message: string; severity: string }[];
  preview: Record<string, unknown>[];
  detected_crs: string | null;
  target_srid: number;
  duplicate_count: number;
};

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function getBaseUrl(): string {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!base) {
    throw new Error(
      "NEXT_PUBLIC_API_BASE_URL is not set. Copy frontend/.env.local.example to .env.local."
    );
  }
  return base.replace(/\/$/, "");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${getBaseUrl()}${path}`;
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.headers || {}),
      },
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiError(
      `Network error talking to API at ${url}`,
      0,
      err instanceof Error ? err.message : err
    );
  }

  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!res.ok) {
    const detail =
      typeof body === "object" && body && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : res.statusText;
    throw new ApiError(detail || "Request failed", res.status, body);
  }

  return body as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  metadata: () => request<MetadataResponse>("/api/metadata"),
  zones: (cityId: string, page = 1, pageSize = 20) =>
    request<ZoneListResponse>(
      withCity(`/api/zones?page=${page}&page_size=${pageSize}`, cityId)
    ),
  zone: (cityId: string, zoneId: string) =>
    request<ZoneOut>(withCity(`/api/zones/${zoneId}`, cityId)),
  zoneExplanation: (cityId: string, zoneId: string) =>
    request<ZoneExplanation>(
      withCity(`/api/zones/${zoneId}/explanation`, cityId)
    ),
  dependencyGraph: (cityId: string, zoneId?: string) =>
    request<DependencyGraph>(
      withCity(
        zoneId
          ? `/api/dependency-graph?zone_id=${encodeURIComponent(zoneId)}`
          : "/api/dependency-graph",
        cityId
      )
    ),
  runAssessments: (
    cityId: string,
    body?: {
      zone_ids?: string[];
      weight_overrides?: Record<string, number>;
      seed_dependency_graph?: boolean;
    }
  ) =>
    request<RunAssessmentsResponse>(withCity("/api/assessments/run", cityId), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    }),
  latestAssessments: (cityId: string) =>
    request<LatestAssessmentsResponse>(
      withCity("/api/assessments/latest", cityId)
    ),
  overview: (cityId: string) =>
    request<OverviewResponse>(withCity("/api/dashboard/overview", cityId)),
  mapLayers: (cityId: string) =>
    request<MapLayersResponse>(withCity("/api/map/layers", cityId)),
  zoneContext: (cityId: string, zoneId: string) =>
    request<ZoneContextResponse>(
      withCity(`/api/zones/${zoneId}/context`, cityId)
    ),
  sources: (cityId: string) =>
    request<DataSourceOut[]>(withCity("/api/data/sources", cityId)),
  exportData: (cityId: string) =>
    request<Record<string, unknown>>(withCity("/api/data/export", cityId)),
  seedSynthetic: (cityId: string) =>
    request<Record<string, unknown>>(
      withCity("/api/data/synthetic/seed", cityId),
      { method: "POST" }
    ),
  validateFile: async (file: File, recordType: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("record_type", recordType);
    return request<ValidationResult>("/api/data/validate", {
      method: "POST",
      body: form,
    });
  },
  importFile: async (
    cityId: string,
    file: File,
    recordType: string,
    commit = true
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("record_type", recordType);
    form.append("commit", String(commit));
    form.append("source_name", `UI import ${file.name}`);
    return request<Record<string, unknown>>(
      withCity("/api/data/import", cityId),
      {
        method: "POST",
        body: form,
      }
    );
  },
  interventions: (cityId: string, zoneId?: string) =>
    request<InterventionListResponse>(
      withCity(
        zoneId
          ? `/api/interventions?zone_id=${encodeURIComponent(zoneId)}`
          : "/api/interventions",
        cityId
      )
    ),
  intervention: (cityId: string, id: string) =>
    request<InterventionScenario>(
      withCity(`/api/interventions/${id}`, cityId)
    ),
  compareIntervention: (
    cityId: string,
    body: {
      zone_id: string;
      intervention_type: string;
      name: string;
      params: Record<string, unknown>;
      notes?: string;
      weight_overrides?: Record<string, number>;
    }
  ) =>
    request<InterventionScenario>(
      withCity("/api/interventions/compare", cityId),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, persist: true }),
      }
    ),
  sensitivity: (cityId: string, perturbation = 0.2) =>
    request<SensitivityResponse>(
      withCity("/api/assessments/sensitivity", cityId),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ perturbation }),
      }
    ),
  cities: () =>
    request<{ default_city_id: string; items: CityProfile[]; notes: string[] }>(
      "/api/cities"
    ),
  ingestOpenMeteo: (cityId: string) =>
    request<Record<string, unknown>>("/api/ingest/weather/open-meteo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ city_id: cityId }),
    }),
  ingestFloodProxy: (cityId: string, horizonHours = 24) =>
    request<Record<string, unknown>>("/api/ingest/flood-labels/proxy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ city_id: cityId, horizon_hours: horizonHours }),
    }),
  ingestReportCorpus: () =>
    request<Record<string, unknown>>("/api/ingest/reports/corpus", {
      method: "POST",
    }),
  trainEarlyWarning: (cityId: string, horizonHours = 24) =>
    request<Record<string, unknown>>("/api/early-warning/train", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ city_id: cityId, horizon_hours: horizonHours }),
    }),
  earlyWarningStatus: (cityId: string, horizonHours = 24) =>
    request<Record<string, unknown>>(
      `/api/early-warning/status?city_id=${encodeURIComponent(cityId)}&horizon_hours=${horizonHours}`
    ),
  earlyWarningPredict: (cityId: string, horizonHours = 24) =>
    request<Record<string, unknown>>(
      `/api/early-warning/predict?city_id=${encodeURIComponent(cityId)}&horizon_hours=${horizonHours}`
    ),
  trainReports: () =>
    request<Record<string, unknown>>("/api/reports/train", { method: "POST" }),
  submitReport: (
    cityId: string,
    body: {
      text: string;
      lon?: number;
      lat?: number;
    }
  ) =>
    request<SubmitReportResponse>(withCity("/api/reports/submit", cityId), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  listReports: (cityId: string, needsReview?: boolean) => {
    const params = new URLSearchParams({ city_id: cityId });
    if (needsReview !== undefined) params.set("needs_review", String(needsReview));
    return request<{
      city_id: string;
      items: CommunityReport[];
      total_returned: number;
    }>(`/api/reports?${params.toString()}`);
  },
  reviewReport: (
    cityId: string,
    id: string,
    body: {
      reviewed?: boolean;
      review_notes?: string;
      verification_status?: string;
    }
  ) =>
    request<CommunityReport>(
      withCity(`/api/reports/${id}/review`, cityId),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    ),
  cascadeSimulate: (
    cityId: string,
    scenarioType: string,
    opts?: { zone_ids?: string[]; failed_infra_ids?: string[] }
  ) =>
    request<Record<string, unknown>>(
      withCity("/api/cascade/simulate", cityId),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario_type: scenarioType,
          zone_ids: opts?.zone_ids,
          failed_infra_ids: opts?.failed_infra_ids,
        }),
      }
    ),
  caseBriefing: (cityId: string, zoneId: string) =>
    request<CaseBriefing>(
      withCity(`/api/zones/${encodeURIComponent(zoneId)}/case`, cityId)
    ),
  caseTasks: (cityId: string, zoneId: string) =>
    request<CaseTasksResponse>(
      withCity(`/api/zones/${encodeURIComponent(zoneId)}/tasks`, cityId)
    ),
  cityTasks: (cityId: string, includeDone = true) =>
    request<CityTasksResponse>(
      withCity(
        `/api/tasks?include_done=${includeDone}`,
        cityId
      )
    ),
  createCaseTask: (
    cityId: string,
    zoneId: string,
    body: {
      title: string;
      description?: string;
      why_recommended?: string;
      priority?: string;
      source?: string;
      source_ref?: string | null;
      assigned_to?: string | null;
      next_step?: string | null;
    }
  ) =>
    request<ResponseTask>(
      withCity(`/api/zones/${encodeURIComponent(zoneId)}/tasks`, cityId),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    ),
  updateCaseTask: (
    cityId: string,
    taskId: string,
    body: {
      status?: string;
      assigned_to?: string | null;
      priority?: string;
      next_step?: string | null;
      note?: string;
    }
  ) =>
    request<ResponseTask>(
      withCity(`/api/tasks/${encodeURIComponent(taskId)}/update`, cityId),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    ),
  caseExportUrl: (cityId: string, zoneId: string, format: "json" | "csv" = "csv") => {
    const base = getBaseUrl();
    return `${base}${withCity(
      `/api/zones/${encodeURIComponent(zoneId)}/case/export?format=${format}`,
      cityId
    )}`;
  },
  resilienceRun: (cityId: string, seed = 42) =>
    request<Record<string, unknown>>(withCity("/api/resilience/run", cityId), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seed }),
    }),
  osmImport: (cityId: string) =>
    request<Record<string, unknown>>(
      `/api/data/osm/import?city_id=${encodeURIComponent(cityId)}&commit=true`,
      { method: "POST" }
    ),
  mlStatus: () => request<Record<string, unknown>>("/api/ml/status"),
  mlClusters: (cityId: string, minCategory = "high") =>
    request<MlClustersResponse>(
      `/api/ml/clusters?city=${encodeURIComponent(cityId)}&min_category=${encodeURIComponent(minCategory)}`
    ),
  mlRankings: (cityId: string, limit = 50) =>
    request<{
      items: MlRankingItem[];
      disclaimer: string;
    }>(
      `/api/ml/rankings?city=${encodeURIComponent(cityId)}&limit=${limit}`
    ),
  mlZoneExplanation: (zoneId: string) =>
    request<Record<string, unknown>>(
      `/api/ml/zones/${encodeURIComponent(zoneId)}/explanation`
    ),
  alerts: (cityId: string, includeResolved = true) =>
    request<AlertsListResponse>(
      withCity(
        `/api/alerts?include_resolved=${includeResolved}`,
        cityId
      )
    ),
  alertsUnreadCount: (cityId: string) =>
    request<{ city_id: string; unread_count: number }>(
      withCity("/api/alerts/unread-count", cityId)
    ),
  alertSources: (cityId: string) =>
    request<AlertSourcesResponse>(withCity("/api/alerts/sources", cityId)),
  alertAction: (
    cityId: string,
    alertId: string,
    action: "read" | "acknowledge" | "resolve"
  ) =>
    request<LiveAlert>(
      withCity(`/api/alerts/${encodeURIComponent(alertId)}/action`, cityId),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      }
    ),
  alertsMarkAllRead: (cityId: string) =>
    request<{ city_id: string; marked: number; unread_count: number }>(
      withCity("/api/alerts/mark-all-read", cityId),
      { method: "POST" }
    ),
  createDemoAlert: (
    cityId: string,
    body?: { alert_type?: string; severity?: string }
  ) =>
    request<{ created: boolean; alert: LiveAlert; disclaimer: string }>(
      withCity("/api/alerts/demo", cityId),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {}),
      }
    ),
  pollAlerts: (cityId: string) =>
    request<{
      city_id: string;
      unread_count: number;
      results: Record<string, unknown>[];
    }>(withCity("/api/alerts/poll", cityId), { method: "POST" }),
  communityRiskOverview: (cityId: string) =>
    request<CommunityRiskOverviewResponse>(
      withCity("/api/community-impact/overview", cityId)
    ),
  alertCommunityImpact: (cityId: string, alertId: string, radiusM?: number) =>
    request<CommunityImpactAnalysisResponse>(
      withCity(
        `/api/community-impact/alert/${encodeURIComponent(alertId)}${
          radiusM ? `?radius_m=${radiusM}` : ""
        }`,
        cityId
      )
    ),
  analyzeCustomCommunityImpact: (
    cityId: string,
    body: {
      alert_id?: string;
      lon?: number;
      lat?: number;
      radius_m?: number;
      alert_type?: string;
    }
  ) =>
    request<CommunityImpactAnalysisResponse>(
      withCity("/api/community-impact/analyze", cityId),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    ),
};

export type LiveAlert = {
  id: string;
  city_id: string;
  source_name: string;
  source_event_id: string;
  alert_type: string;
  severity: string;
  title: string;
  description: string;
  lon: number | null;
  lat: number | null;
  has_reliable_coords: boolean;
  zone_id: string | null;
  zone_code: string | null;
  area_label: string | null;
  source_url: string | null;
  verification_status: string;
  authenticity: string;
  is_demo: boolean;
  observed_at: string | null;
  published_at: string | null;
  ingested_at: string | null;
  is_read: boolean;
  is_acknowledged: boolean;
  is_resolved: boolean;
  resolved_at: string | null;
  extra: Record<string, unknown>;
  display_label: string | null;
};

export type AlertsListResponse = {
  city_id: string;
  unread_count: number;
  items: LiveAlert[];
  disclaimer: string;
};

export type AlertSourcesResponse = {
  city_id: string;
  sources: {
    id: string;
    label: string;
    kind: string;
    official: boolean;
    last_alert_at: string | null;
    notes: string;
  }[];
  stale_after_hours: number;
  generated_at: string;
};

export type ResponseTask = {
  id: string;
  city_id: string;
  zone_id: string;
  title: string;
  description: string;
  why_recommended: string;
  priority: string;
  status: string;
  source: string;
  source_ref: string | null;
  assigned_to: string | null;
  next_step: string | null;
  notes: { at: string; text: string }[];
  audit: { at: string; action: string; detail: string }[];
  completed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  disclaimer: string;
  zone_name?: string;
  zone_code?: string;
};

export type CityTasksResponse = {
  city_id: string;
  items: ResponseTask[];
  disclaimer: string;
};

export type SuggestedTask = {
  title: string;
  description: string;
  why_recommended: string;
  priority: string;
  source: string;
  source_ref: string | null;
  next_step: string;
};

export type CaseTasksResponse = {
  zone_id: string;
  city_id: string;
  items: ResponseTask[];
  suggested: SuggestedTask[];
  disclaimer: string;
};

export type CaseBriefing = {
  zone_id: string;
  city_id: string;
  zone_code: string;
  zone_name: string;
  description: string | null;
  operational_status: string;
  category: string | null;
  overall_score: number | null;
  score_kind: string;
  is_synthetic: boolean | null;
  data_source_name: string | null;
  last_assessment_at: string | null;
  confidence: number | null;
  plain_language_why: string;
  situation_types: {
    predicted_risk: boolean;
    observed_incident: boolean;
    confirmed_official_alert: boolean;
    demo_or_synthetic: boolean;
  };
  impact: {
    population: {
      value: number | null;
      label: string;
      is_demo_estimate: boolean;
    };
    nearest_healthcare_km: number | null;
    nearest_healthcare_name: string | null;
    nearest_healthcare_note: string;
    hospitals_clinics_in_zone: {
      id: string;
      name: string;
      kind: string;
      is_synthetic: boolean;
      geometry?: Record<string, unknown> | null;
    }[];
    roads_in_zone: {
      id: string;
      name: string;
      kind: string;
      is_synthetic: boolean;
      geometry?: Record<string, unknown> | null;
    }[];
    roads_blocked_reported: string;
    roads_blocked_note: string;
    hazard_observations: {
      id: string;
      name: string;
      kind: string;
      is_synthetic: boolean;
      extra?: Record<string, unknown>;
      geometry?: Record<string, unknown> | null;
    }[];
    all_infrastructure: {
      id: string;
      name: string;
      kind: string;
      is_synthetic: boolean;
      geometry?: Record<string, unknown> | null;
    }[];
  };
  incidents: {
    alerts: {
      id: string;
      title: string;
      description: string;
      severity: string;
      authenticity: string;
      is_demo: boolean;
      is_acknowledged: boolean;
      is_resolved: boolean;
      has_reliable_coords: boolean;
      lat: number | null;
      lon: number | null;
      source_name: string;
      observed_at: string | null;
      ingested_at: string | null;
      kind_label: string;
    }[];
    community_reports: {
      id: string;
      category: string;
      text_redacted: string;
      verification_status: string;
      needs_human_review: boolean;
      lat?: number | null;
      lon?: number | null;
      created_at: string | null;
      kind_label: string;
    }[];
    unresolved_alert_count: number;
    unverified_report_count: number;
  };
  data_gaps: string[];
  tasks: ResponseTask[];
  suggested_tasks: SuggestedTask[];
  geojson: Record<string, unknown> | null;
  generated_at: string;
  disclaimer: string;
};

export type MlRankingItem = {
  zone_id: string;
  city: string;
  latitude: number;
  longitude: number;
  risk_score: number | null;
  risk_category: string | null;
  anomaly_score: number | null;
  anomaly_flag: boolean;
  source_coverage_score: number | null;
  data_quality_flag: string | null;
};

export type MlClustersResponse = {
  type: string;
  features: {
    type: string;
    geometry: { type?: string; coordinates?: number[] } | null;
    properties: Record<string, unknown>;
  }[];
  members?: GeoJsonFeatureCollection;
  meta?: Record<string, unknown>;
  clusters?: Record<string, unknown>[];
};

export type CityProfile = {
  id: string;
  name: string;
  country: string;
  bbox: { west: number; south: number; east: number; north: number };
  centroid: { lon: number; lat: number };
  timezone: string;
  notes: string;
};

export type CommunityReport = {
  id: string;
  city_id: string;
  text_redacted: string;
  category: string;
  disaster_related: boolean | null;
  disaster_related_proba: number | null;
  labels: string[];
  label_probas?: Record<string, number>;
  needs_human_review: boolean;
  reviewed: boolean;
  review_notes?: string | null;
  verification_status: string;
  location_precision: string;
  location?: Record<string, unknown>;
  has_map_marker?: boolean;
  observation_kind: string;
  source_reliability?: string;
  observed_at?: string | null;
  created_at: string | null;
};

export type SubmitReportResponse = {
  id: string;
  city_id: string;
  category: string;
  verification_status: string;
  needs_human_review: boolean;
  created_at: string | null;
  location_precision: string;
  has_map_marker: boolean;
  stored_text_redacted_only: boolean;
  report: CommunityReport;
  disclaimer: string;
  classification?: Record<string, unknown>;
};

export type AffectedCommunity = {
  zone_id: string;
  zone_code: string;
  zone_name: string;
  distance_m: number;
  distance_km: number;
  centroid: { lon: number; lat: number };
  boundary_geojson?: Record<string, unknown> | null;
  vulnerability_score: number | null;
  vulnerability_category: string;
  impact_severity: "critical" | "high" | "moderate" | "low" | "unknown";
  impact_color: string;
  confidence: number | null;
  is_synthetic: boolean;
  data_source_name: string;
  top_vulnerability_factors: string[];
  reasons: string[];
  explanation: string;
  assessment_available: boolean;
  hazard_only_score?: number | null;
  hazard_only_rank?: number | null;
  multifactor_rank?: number | null;
  rank_uplift?: number | null;
};

export type AffectedInfrastructure = {
  id: string;
  name: string;
  kind: string;
  distance_m: number;
  distance_km: number;
  centroid: { lon: number; lat: number };
  is_synthetic: boolean;
  data_source_name: string;
};

export type DependencyPathwayStep = {
  source: string;
  target: string;
  relation: string;
};

export type CommunityImpactAnalysisResponse = {
  city_id: string;
  city_name: string;
  alert?: {
    id: string;
    title: string;
    alert_type: string;
    severity: string;
    is_demo: boolean;
    authenticity: string;
    area_label: string | null;
    description: string;
    observed_at?: string | null;
    lon: number | null;
    lat: number | null;
  } | null;
  analysis_point: {
    lon: number;
    lat: number;
    has_coordinates: boolean;
    note: string;
  };
  impact_radius_m: number;
  impact_context: {
    primary_concern: string;
    infrastructure_focus: string[];
    impact_factors: string[];
    dependency_pathway: DependencyPathwayStep[];
    cascading_mechanism: string;
  };
  overall_severity: "critical" | "high" | "moderate" | "low";
  overall_severity_color: string;
  summary: {
    total_communities_affected: number;
    severity_breakdown: Record<string, number>;
    max_vulnerability_score: number | null;
    average_vulnerability_score: number | null;
    total_infrastructure_in_radius: number;
    healthcare_facilities_in_radius: number;
    roads_in_radius: number;
    synthetic_data_count: number;
  };
  affected_communities: AffectedCommunity[];
  affected_infrastructure: AffectedInfrastructure[];
  affected_zones_geojson?: GeoJsonFeatureCollection;
  recommendations: {
    priority: "urgent" | "high" | "medium" | "info";
    action: string;
    reason: string;
  }[];
  impact_circle_geojson: {
    type: string;
    geometry: {
      type: string;
      coordinates: number[][][];
    };
    properties: Record<string, unknown>;
  };
  generated_at: string;
  disclaimers: string[];
};

export type CommunityRiskItem = {
  zone_id: string;
  zone_code: string;
  zone_name: string;
  centroid: { lon: number; lat: number };
  boundary_geojson?: Record<string, unknown> | null;
  vulnerability_score: number | null;
  vulnerability_category: string;
  impact_severity: "critical" | "high" | "moderate" | "low" | "unknown";
  impact_color: string;
  confidence: number | null;
  is_synthetic: boolean;
  data_source_name: string;
  top_vulnerability_factors: string[];
  reasons: string[];
  explanation: string;
  assessment_available: boolean;
  hazard_only_score?: number | null;
  hazard_only_rank?: number | null;
  multifactor_rank?: number | null;
  rank_uplift?: number | null;
  nearby_active_alerts: {
    id: string;
    title: string;
    alert_type: string;
    severity: string;
    distance_km: number;
    is_demo: boolean;
  }[];
  has_active_threat: boolean;
};

export type CommunityRiskOverviewResponse = {
  city_id: string;
  city_name: string;
  total_communities: number;
  severity_breakdown: Record<string, number>;
  average_vulnerability_score: number | null;
  max_vulnerability_score: number | null;
  active_alerts_count: number;
  synthetic_data_count: number;
  communities: CommunityRiskItem[];
  generated_at: string;
  disclaimer: string;
};


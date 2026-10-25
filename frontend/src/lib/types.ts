/** Shared Module 2 types for assessments, explanations, and dependency graphs. */

export type ComponentScore = {
  key: string;
  label: string;
  status: "available" | "unavailable" | "synthetic" | string;
  raw_value: number | null;
  normalized_score: number | null;
  weight_configured: number;
  weight_effective: number;
  direction: string;
  is_synthetic: boolean;
  contribution: number | null;
  reason: string;
  source_refs: string[];
  limitations: string;
};

export type DataQuality = {
  components_configured?: number;
  components_available?: number;
  components_unavailable?: number;
  components_synthetic?: number;
  weight_coverage?: number;
  weights_renormalized?: boolean;
  [key: string]: unknown;
};

export type Assessment = {
  id: string;
  run_id: string;
  zone_id: string;
  zone_code: string | null;
  zone_name: string | null;
  scoring_version: string;
  overall_score: number | null;
  category: string | null;
  confidence: number;
  components: ComponentScore[];
  weights_used: Record<string, number>;
  reasons: string[];
  data_quality: DataQuality;
  limitations: string[];
  source_refs: string[];
  inputs: Record<string, unknown>;
  explanation: string;
  created_at: string;
};

export type ZoneExplanation = {
  zone_id: string;
  zone_code: string;
  zone_name: string;
  assessment: Assessment | null;
  message: string | null;
};

export type RunAssessmentsResponse = {
  run_id: string;
  scoring_version: string;
  assessed: number;
  assessments: Assessment[];
  methodology: Record<string, unknown>;
  dependency_graph_seeded: boolean;
};

export type LatestAssessmentsResponse = {
  scoring_version: string | null;
  run_id: string | null;
  items: Assessment[];
  total: number;
};

export type GraphNode = {
  id: string;
  label: string;
  kind: string;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  relationship_type: string;
  evidence: string | null;
  evidence_kind: "observed" | "assumed" | "hypothesized" | string;
  strength: number | null;
  confidence: number | null;
  provenance: Record<string, unknown>;
  zone_id: string | null;
};

export type DependencyGraph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  cycles: string[][];
  is_dag: boolean;
  notes: string[];
  generated_at: string;
};

export type OverviewResponse = {
  city_id: string;
  total_zones: number;
  zones_assessed: number;
  category_counts: { category: string; count: number; label: string }[];
  high_priority: {
    zone_id: string;
    code: string;
    name: string;
    overall_score: number | null;
    category: string | null;
    is_synthetic: boolean | null;
    confidence: number | null;
    hazard_only_score?: number | null;
    hazard_only_rank?: number | null;
    multifactor_rank?: number | null;
    rank_uplift?: number | null;
  }[];
  healthcare: {
    zones_with_travel_burden: number;
    average_nearest_healthcare_km: number | null;
    note: string;
  };
  freshness: {
    latest_assessment_at: string | null;
    latest_run_id: string | null;
    scoring_version: string | null;
    data_source_count: number;
    synthetic_source_count: number;
    authentic_source_count: number;
  };
  key_findings: string[];
  map_preview_zone_ids: string[];
  disclaimer: string;
};

export type GeoJsonFeatureCollection = {
  type: "FeatureCollection" | string;
  features: {
    type: string;
    geometry: Record<string, unknown> | null;
    properties: Record<string, unknown>;
  }[];
  meta?: Record<string, unknown>;
};

export type MapLayersResponse = {
  city_id: string;
  zones: GeoJsonFeatureCollection;
  hazards: GeoJsonFeatureCollection;
  infrastructure: GeoJsonFeatureCollection;
  community_reports?: GeoJsonFeatureCollection;
  generated_at: string;
  notes: string[];
};

export type ZoneContextItem = {
  id: string;
  name: string;
  kind: string;
  is_synthetic: boolean;
  data_source_name: string | null;
  properties: Record<string, unknown>;
  geometry: Record<string, unknown> | null;
  extra: Record<string, unknown>;
};

export type ZoneContextResponse = {
  zone_id: string;
  zone_code: string;
  zone_name: string;
  is_synthetic: boolean | null;
  hazards: ZoneContextItem[];
  infrastructure: ZoneContextItem[];
  note: string;
};

export type InterventionScenario = {
  id: string;
  zone_id: string;
  zone_code: string | null;
  zone_name: string | null;
  name: string;
  intervention_type: string;
  scoring_version: string;
  assumptions: Record<string, unknown>;
  inputs: Record<string, unknown>;
  baseline: Record<string, unknown>;
  results: Record<string, unknown>;
  limitations: string[] | Record<string, unknown>;
  provenance: Record<string, unknown>;
  notes: string | null;
  created_at: string;
  simulation_label: string;
};

export type InterventionListResponse = {
  items: InterventionScenario[];
  total: number;
  catalog: Record<string, unknown>[];
};

export type SensitivityResponse = {
  method: string;
  perturbation: number | null;
  disclaimer: string;
  assumptions: string[];
  baseline_ranking: {
    zone_id: string;
    zone_code: string;
    zone_name: string;
    overall_score: number | null;
    category: string | null;
  }[];
  baseline_top3: string[];
  variants: Record<string, unknown>[];
  summary: Record<string, unknown>;
};

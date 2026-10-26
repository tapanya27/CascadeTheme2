/**
 * Scenario-specific interpretation of cascade simulation API results.
 * Driven by actual backend fields — does not invent incidents or geography.
 */

export type CascadeSeverity = "low" | "moderate" | "high" | "critical" | "unknown";

export type FailedAsset = {
  id: string;
  name: string;
  infrastructure_type: string;
  city_id?: string;
  is_synthetic?: boolean;
  properties?: Record<string, unknown>;
  geometry?: GeoJSON.Geometry | null;
};

export type SelectedRoute = {
  id: string;
  name: string;
  route_number?: string | null;
  origin?: string | null;
  destination?: string | null;
  stops?: string[];
  geometry?: GeoJSON.Geometry | null;
  is_synthetic?: boolean;
};

export type SelectedPowerAsset = {
  id: string;
  name: string;
  geometry?: GeoJSON.Geometry | null;
  is_synthetic?: boolean;
  service_label?: string | null;
};

export type ZoneImpact = {
  zone_id: string;
  zone_code?: string | null;
  zone_name?: string | null;
  display_name?: string | null;
  name_unavailable?: boolean;
  baseline_multifactor_score?: number | null;
  scenario_multifactor_score?: number | null;
  delta_multifactor_score?: number | null;
  score_direction?: "worsened" | "improved" | "unchanged" | "unknown" | string;
  score_name?: string;
  score_meaning?: string;
  higher_is_worse?: boolean;
  baseline_category?: string | null;
  scenario_category?: string | null;
  failed_affecting_zone?: boolean;
  service_effects?: string[];
  baseline_confidence?: number | null;
  scenario_confidence?: number | null;
  healthcare_notes?: string | null;
  road_notes?: string | null;
  flood_notes?: string | null;
  power_assumption?: string | null;
  limitations?: unknown;
};

export type CascadeResult = {
  scenario_id?: string;
  city_id?: string | null;
  scenario_type: string;
  simulation_label?: string;
  illustrative?: boolean;
  created_at?: string;
  failed_infra_ids?: string[];
  failed_assets?: FailedAsset[];
  selected_route?: SelectedRoute | null;
  selected_power_asset?: SelectedPowerAsset | null;
  lost_source_kinds?: string[];
  data_gaps?: string[];
  dependency_explanations?: Record<string, unknown>[];
  zone_impacts?: ZoneImpact[];
  impact_totals?: {
    communities_checked?: number;
    communities_with_change?: number;
    communities_worsened?: number;
    communities_with_confidence_drop?: number;
    communities_directly_linked_to_failed_assets?: number;
  };
  score_scale?: {
    name?: string;
    range?: string;
    higher_is_worse?: boolean;
    categories?: { key: string; min: number; max: number }[];
    note?: string;
  };
  assumptions?: string[];
  concepts_separated?: Record<string, string>;
  [key: string]: unknown;
};

export type ActionItem = {
  id: string;
  action: string;
  reason: string;
  areaOrService: string;
  role: string;
  priority: "low" | "medium" | "high" | "urgent";
  verificationStatus: "recommended" | "needs_field_check";
  zoneId?: string;
};

export type InterpretedZone = {
  zoneId: string;
  title: string;
  zoneCode: string | null;
  nameUnavailable: boolean;
  severity: CascadeSeverity;
  direction: string;
  services: string[];
  explanation: string;
  recommendedAction: string | null;
  baselineScore: number | null;
  scenarioScore: number | null;
  delta: number | null;
  baselineCategory: string | null;
  scenarioCategory: string | null;
  scoreName: string;
  scoreMeaning: string;
  higherIsWorse: boolean;
};

export type InterpretedCascade = {
  scenarioType: string;
  whatHappened: string;
  howSerious: CascadeSeverity;
  severityExplanation: string;
  severityProvisional: boolean;
  whatIsAffected: string[];
  whyItMatters: string;
  whatShouldWeDo: string[];
  whatNeedsVerification: string[];
  whatHappensNext: string[];
  assumptionsDisclosed: string[];
  dataGaps: string[];
  illustrative: boolean;
  isDataQualityScenario: boolean;
  zones: InterpretedZone[];
  actions: ActionItem[];
  failedAssets: FailedAsset[];
  selectedRoute: SelectedRoute | null;
  selectedPowerAsset: SelectedPowerAsset | null;
  cityId: string | null;
  scenarioId: string | null;
  scoreScaleNote: string;
  primaryNextStep: string;
};

const SCENARIO_META: Record<
  string,
  { title: string; oneLiner: (ctx: string) => string }
> = {
  road_closure: {
    title: "Road closure",
    oneLiner: (ctx) =>
      `We simulated a road becoming harder to use${ctx ? ` (${ctx})` : ""} and recalculated community access scores for this city.`,
  },
  hospital_outage: {
    title: "Hospital inaccessible",
    oneLiner: (ctx) =>
      `We simulated a hospital/clinic becoming inaccessible${ctx ? ` (${ctx})` : ""} and recalculated healthcare-access burden for linked communities.`,
  },
  multi_failure: {
    title: "Several essential services fail together",
    oneLiner: (ctx) =>
      `We simulated a road and a healthcare facility failing together${ctx ? ` (${ctx})` : ""} to show combined pressure on communities.`,
  },
  bus_service_disruption: {
    title: "Bus service disruption",
    oneLiner: (ctx) =>
      ctx
        ? `We simulated a bus-service disruption on ${ctx} and recalculated access burden for nearby communities in this city.`
        : "No bus-route record is available for this city, so this run is labelled illustrative — we did not invent a route name, stops, or geometry.",
  },
  power_failure: {
    title: "Power failure",
    oneLiner: (ctx) =>
      ctx
        ? `We simulated a power-related disruption near ${ctx} and estimated stress on linked facilities and communities.`
        : "No power-asset record is available for this city, so this run is illustrative — not a real electrical-grid outage model.",
  },
  weather_source_loss: {
    title: "Weather information goes missing",
    oneLiner: () =>
      "We removed weather/hazard inputs for this city. Missing information lowers assessment confidence — it does not mean a flood or storm has occurred.",
  },
  infrastructure_source_loss: {
    title: "Facility information becomes unavailable",
    oneLiner: () =>
      "We suppressed facility records for this city so accessibility rankings become incomplete. This is a data-gap drill, not a confirmed outage.",
  },
};

function assetLabel(assets: FailedAsset[]): string {
  if (!assets.length) return "";
  return assets
    .map((a) => `${a.name} (${a.infrastructure_type.replace(/_/g, " ")})`)
    .join("; ");
}

function serviceLabel(effect: string): string {
  const map: Record<string, string> = {
    road_access_worsened: "Road access",
    healthcare_access_worsened: "Healthcare access",
    facility_count_reduced: "Nearby facilities",
    hazard_data_unavailable: "Weather / hazard information",
    facility_data_unavailable: "Facility records",
    illustrative_service_availability_drop: "Illustrative service availability",
    bus_access_worsened: "Bus / transit access",
    power_dependent_facility_stress: "Power-dependent facilities",
    bus_route_data_unavailable: "Bus route data missing",
  };
  return map[effect] ?? effect.replace(/_/g, " ");
}

function categoryRank(cat: string | null | undefined): number {
  switch (cat) {
    case "critical":
      return 4;
    case "high":
      return 3;
    case "moderate":
      return 2;
    case "low":
      return 1;
    default:
      return 0;
  }
}

function zoneSeverity(z: ZoneImpact, isDataQuality: boolean): CascadeSeverity {
  if (isDataQuality) {
    const drop =
      z.baseline_confidence != null &&
      z.scenario_confidence != null &&
      z.scenario_confidence < z.baseline_confidence - 0.01;
    if (drop && categoryRank(z.baseline_category) >= 3) return "high";
    if (drop) return "moderate";
    if ((z.service_effects || []).length) return "moderate";
    return "low";
  }
  const scen = z.scenario_category;
  const delta = z.delta_multifactor_score;
  if (scen === "critical" && delta != null && delta > 0) return "critical";
  if (scen === "high" && delta != null && delta > 2) return "high";
  if (delta != null && delta >= 8) return "high";
  if (delta != null && delta >= 3) return "moderate";
  if (z.failed_affecting_zone || (delta != null && Math.abs(delta) > 0.05))
    return "moderate";
  if (delta != null && Math.abs(delta) > 0) return "low";
  return "unknown";
}

/**
 * Provisional overall severity from validated score categories + impact counts.
 * Never Critical solely because a number moved.
 */
export function overallSeverity(
  result: CascadeResult,
  isDataQuality: boolean
): { level: CascadeSeverity; explanation: string; provisional: boolean } {
  const totals = result.impact_totals;
  const worsened = totals?.communities_worsened ?? 0;
  const linked = totals?.communities_directly_linked_to_failed_assets ?? 0;
  const confDrop = totals?.communities_with_confidence_drop ?? 0;
  const gaps = result.data_gaps?.length ?? 0;
  const zones = result.zone_impacts ?? [];
  const maxCat = Math.max(0, ...zones.map((z) => categoryRank(z.scenario_category)));
  const maxDelta = Math.max(
    0,
    ...zones.map((z) => Math.max(0, Number(z.delta_multifactor_score ?? 0)))
  );

  if (gaps && (totals?.communities_checked ?? 0) === 0) {
    return {
      level: "unknown",
      explanation:
        "Not enough city data to judge impact. See missing-data notes below.",
      provisional: true,
    };
  }

  if (isDataQuality) {
    if (confDrop >= 10 || (confDrop > 0 && maxCat >= 3)) {
      return {
        level: "high",
        explanation:
          "Many assessments lose confidence or high-priority communities lose key inputs. This is an information-risk level — not a confirmed disaster.",
        provisional: true,
      };
    }
    if (confDrop > 0 || (result.lost_source_kinds?.length ?? 0) > 0) {
      return {
        level: "moderate",
        explanation:
          "Missing inputs reduce how complete the assessment is. Officers should verify weather or facility records before relying on rankings.",
        provisional: true,
      };
    }
    return {
      level: "low",
      explanation: "Little change in completeness for this city under the data-gap drill.",
      provisional: true,
    };
  }

  if (maxCat >= 4 && worsened >= 1 && maxDelta >= 5) {
    return {
      level: "critical",
      explanation:
        "At least one linked community moves into the critical vulnerability band with a meaningful simulated score increase.",
      provisional: true,
    };
  }
  if ((worsened >= 3 && maxDelta >= 3) || (linked >= 2 && maxCat >= 3)) {
    return {
      level: "high",
      explanation:
        "Several communities show worsened simulated vulnerability, or high-band communities are directly linked to the failed asset.",
      provisional: true,
    };
  }
  if (worsened >= 1 || linked >= 1 || maxDelta >= 1) {
    return {
      level: "moderate",
      explanation:
        "Some communities show a simulated access or vulnerability change. Review linked areas and verify on the ground.",
      provisional: true,
    };
  }
  if (result.illustrative) {
    return {
      level: "low",
      explanation:
        "Illustrative assumption applied; limited measured change in this city's data.",
      provisional: true,
    };
  }
  return {
    level: "low",
    explanation:
      "Few or no community scores moved. Failed assets may not be spatially linked to zones in this city's data.",
    provisional: true,
  };
}

function zoneTitle(z: ZoneImpact): string {
  if (z.display_name) return z.display_name;
  if (z.zone_name) return z.zone_name;
  return `Community ${z.zone_code || z.zone_id.slice(0, 8)}`;
}

function interpretZone(
  z: ZoneImpact,
  scenarioType: string,
  isDataQuality: boolean
): InterpretedZone {
  const services = (z.service_effects || []).map(serviceLabel);
  const direction = z.score_direction || "unknown";
  const title = zoneTitle(z);
  const nameUnavailable = Boolean(
    z.name_unavailable || (!z.zone_name && !z.display_name?.includes(" "))
  );

  let explanation = "";
  if (isDataQuality && scenarioType === "weather_source_loss") {
    explanation =
      "Hazard/weather inputs were removed for scoring. Rankings here are less complete — this is not evidence that flooding is occurring in this community.";
    if (direction === "improved" || (z.delta_multifactor_score != null && z.delta_multifactor_score < 0)) {
      explanation +=
        " A lower score here usually means the hazard factor dropped out of the model, not that conditions became safer on the ground.";
    }
  } else if (isDataQuality && scenarioType === "infrastructure_source_loss") {
    explanation =
      "Facility records were suppressed. Distance-to-care and facility-count factors cannot be trusted until records are verified.";
  } else if (direction === "worsened") {
    explanation = `Simulated vulnerability rose from ${fmt(z.baseline_multifactor_score)} to ${fmt(z.scenario_multifactor_score)} (higher = more concerning).`;
  } else if (direction === "improved") {
    explanation = `Simulated vulnerability fell from ${fmt(z.baseline_multifactor_score)} to ${fmt(z.scenario_multifactor_score)}. Unusual for a failure drill — treat as model sensitivity, not a real improvement.`;
  } else if (z.failed_affecting_zone) {
    explanation =
      "This community is spatially linked to a failed asset (within ~2 km), but the composite score barely moved.";
  } else {
    explanation = "Little or no simulated score change for this community.";
  }

  if (z.road_notes) explanation += ` ${z.road_notes}`;
  if (z.healthcare_notes) explanation += ` ${z.healthcare_notes}`;
  if (z.power_assumption) explanation += ` ${z.power_assumption}`;

  let recommendedAction: string | null = null;
  if (scenarioType === "road_closure" && (z.failed_affecting_zone || direction === "worsened")) {
    recommendedAction =
      "Verify whether the road is actually closed and check access to critical facilities for this community.";
  } else if (
    scenarioType === "hospital_outage" &&
    (z.failed_affecting_zone || direction === "worsened")
  ) {
    recommendedAction =
      "Confirm hospital/clinic availability and identify backup care options using verified facility lists.";
  } else if (scenarioType === "multi_failure" && direction === "worsened") {
    recommendedAction =
      "Coordinate road and health checks for this community — combined pressure needs joint verification.";
  } else if (scenarioType === "weather_source_loss") {
    recommendedAction =
      "Obtain verified weather/hazard information before using this community's hazard-driven ranking.";
  } else if (scenarioType === "infrastructure_source_loss") {
    recommendedAction =
      "Restore or verify facility records for this area before deciding on access-based priorities.";
  } else if (scenarioType === "bus_service_disruption" && (z.failed_affecting_zone || direction === "worsened")) {
    recommendedAction =
      "Confirm whether this bus service is actually disrupted and check how residents reach essential facilities.";
  } else if (scenarioType === "power_failure" && (z.failed_affecting_zone || direction === "worsened")) {
    recommendedAction =
      "Verify power status for essential facilities serving this community; do not treat this as a confirmed grid outage map.";
  }

  return {
    zoneId: z.zone_id,
    title,
    zoneCode: z.zone_code ?? null,
    nameUnavailable:
      nameUnavailable ||
      Boolean(!z.zone_name && z.zone_code && title.startsWith("Community ")),
    severity: zoneSeverity(z, isDataQuality),
    direction,
    services: services.length
      ? services
      : z.failed_affecting_zone
        ? ["Linked to failed asset"]
        : [],
    explanation: explanation.trim(),
    recommendedAction,
    baselineScore: z.baseline_multifactor_score ?? null,
    scenarioScore: z.scenario_multifactor_score ?? null,
    delta: z.delta_multifactor_score ?? null,
    baselineCategory: z.baseline_category ?? null,
    scenarioCategory: z.scenario_category ?? null,
    scoreName: z.score_name || "Multi-factor vulnerability score",
    scoreMeaning:
      z.score_meaning ||
      "Relative vulnerability (0–100). Higher is more concerning.",
    higherIsWorse: z.higher_is_worse !== false,
  };
}

function fmt(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toFixed(1);
}

function buildActions(
  result: CascadeResult,
  zones: InterpretedZone[],
  isDataQuality: boolean
): ActionItem[] {
  const actions: ActionItem[] = [];
  const assets = result.failed_assets || [];
  const type = result.scenario_type;

  if (result.data_gaps?.length) {
    actions.push({
      id: "gap-data",
      action: "Fill missing city data before relying on this drill",
      reason: result.data_gaps.join(" "),
      areaOrService: "City dataset",
      role: "Data / GIS officer",
      priority: "high",
      verificationStatus: "needs_field_check",
    });
  }

  if (type === "road_closure") {
    actions.push({
      id: "road-verify",
      action: "Verify the simulated road status on the ground",
      reason: assets.length
        ? `Simulation used: ${assetLabel(assets)}`
        : "No city road asset was available to bind this scenario.",
      areaOrService: assets[0]?.name || "Road network",
      role: "Field verification officer / Public Works",
      priority: "high",
      verificationStatus: "needs_field_check",
    });
    actions.push({
      id: "road-access",
      action: "Review access routes to hospitals and emergency facilities",
      reason: "Road disruption can lengthen journeys to care in linked communities.",
      areaOrService: "Critical facilities access",
      role: "Transport / Health coordination",
      priority: "medium",
      verificationStatus: "recommended",
    });
  } else if (type === "hospital_outage") {
    actions.push({
      id: "hosp-verify",
      action: "Confirm whether the facility is actually unavailable",
      reason: assets.length
        ? `Simulation used: ${assetLabel(assets)}`
        : "No hospital/clinic asset was available in this city.",
      areaOrService: assets[0]?.name || "Healthcare facility",
      role: "Health department / Facility admin",
      priority: "urgent",
      verificationStatus: "needs_field_check",
    });
    actions.push({
      id: "hosp-alt",
      action: "Identify alternate care only from verified facility lists",
      reason:
        "This model does not invent alternate hospitals unless they exist in the city data.",
      areaOrService: "Healthcare access",
      role: "Health coordination desk",
      priority: "high",
      verificationStatus: "recommended",
    });
  } else if (type === "multi_failure") {
    actions.push({
      id: "multi-coord",
      action: "Run a joint road + health verification for top communities",
      reason: "Combined failures compound access pressure in the simulation.",
      areaOrService: assetLabel(assets) || "Road + hospital",
      role: "Emergency operations coordination",
      priority: "urgent",
      verificationStatus: "needs_field_check",
    });
  } else if (type === "bus_service_disruption") {
    const route = result.selected_route;
    actions.push({
      id: "bus-verify",
      action: route
        ? `Confirm status of bus service ${route.route_number || route.name}`
        : "Locate official bus-route data before treating this drill as operational",
      reason: route
        ? `Simulation used city route record${route.is_synthetic ? " (demo / synthetic)" : ""}${
            route.origin && route.destination
              ? `: ${route.origin} → ${route.destination}`
              : ""
          }.`
        : "No bus-route asset exists for this city — results are illustrative only.",
      areaOrService: route?.name || "Bus service",
      role: "Transport / public transit desk",
      priority: route ? "high" : "medium",
      verificationStatus: "needs_field_check",
    });
    actions.push({
      id: "bus-access",
      action: "Check how nearby communities reach hospitals and markets without this service",
      reason:
        "The model estimates access burden near the route; it does not invent alternate buses.",
      areaOrService: "Community access to essential services",
      role: "Field verification officer",
      priority: "medium",
      verificationStatus: "recommended",
    });
  } else if (type === "power_failure") {
    const power = result.selected_power_asset;
    actions.push({
      id: "power-verify",
      action: power
        ? `Verify status of ${power.name}`
        : "Confirm whether any real power outage exists before acting on this drill",
      reason: power
        ? `Simulation used city power asset${power.is_synthetic ? " (demo / synthetic)" : ""}. Not a full grid topology.`
        : "No power-asset record for this city — facility stress was an illustrative assumption.",
      areaOrService: power?.name || "Power supply",
      role: "Electricity utility / emergency ops",
      priority: power ? "urgent" : "medium",
      verificationStatus: "needs_field_check",
    });
    actions.push({
      id: "power-facilities",
      action: "Check essential facilities that may depend on local power",
      reason:
        "Linked hospitals/clinics may face operational stress — verify on the ground.",
      areaOrService: "Essential facilities",
      role: "Health / facility admin",
      priority: "high",
      verificationStatus: "recommended",
    });
  } else if (type === "weather_source_loss") {
    actions.push({
      id: "wx-verify",
      action: "Obtain verified weather / hazard information for this city",
      reason:
        "Missing hazard inputs reduce confidence — they do not confirm a hazardous condition.",
      areaOrService: "Weather / hazard feeds",
      role: "Meteorology / hazard desk",
      priority: "high",
      verificationStatus: "needs_field_check",
    });
    actions.push({
      id: "wx-review",
      action: "Re-check risk assessments after weather data is restored",
      reason: "Rankings that depended on flood markers may be incomplete until inputs return.",
      areaOrService: "Community risk assessments",
      role: "Disaster management analyst",
      priority: "medium",
      verificationStatus: "recommended",
    });
  } else if (type === "infrastructure_source_loss") {
    actions.push({
      id: "infra-verify",
      action: "Verify hospital and road facility records before deciding",
      reason: "Accessibility rankings are incomplete without facility data.",
      areaOrService: "Facility registry",
      role: "GIS / Health facilities desk",
      priority: "high",
      verificationStatus: "needs_field_check",
    });
  }

  const priorityZones = zones
    .filter((z) => z.severity === "critical" || z.severity === "high")
    .slice(0, 5);
  for (const z of priorityZones) {
    if (!z.recommendedAction) continue;
    actions.push({
      id: `zone-${z.zoneId}`,
      action: z.recommendedAction,
      reason: z.explanation.slice(0, 220),
      areaOrService: z.title,
      role: isDataQuality ? "Analyst / field verifier" : "Field verification officer",
      priority: z.severity === "critical" ? "urgent" : "high",
      verificationStatus: "needs_field_check",
      zoneId: z.zoneId,
    });
  }

  return actions;
}

export function interpretCascade(result: CascadeResult): InterpretedCascade {
  const type = result.scenario_type;
  const meta = SCENARIO_META[type] || {
    title: type,
    oneLiner: () => `Simulated scenario “${type}” for this city.`,
  };
  const assets = result.failed_assets || [];
  const isDataQuality =
    type === "weather_source_loss" || type === "infrastructure_source_loss";
  const severity = overallSeverity(result, isDataQuality);

  const zonesRaw = [...(result.zone_impacts || [])].sort((a, b) => {
    const da = Math.abs(Number(a.delta_multifactor_score ?? 0));
    const db = Math.abs(Number(b.delta_multifactor_score ?? 0));
    if (db !== da) return db - da;
    return categoryRank(b.scenario_category) - categoryRank(a.scenario_category);
  });

  const focusZones = zonesRaw.filter(
    (z) =>
      z.failed_affecting_zone ||
      (z.delta_multifactor_score != null && z.delta_multifactor_score !== 0) ||
      (z.service_effects && z.service_effects.length > 0) ||
      (z.baseline_confidence != null &&
        z.scenario_confidence != null &&
        z.scenario_confidence < z.baseline_confidence - 0.01)
  );
  const zones = (focusZones.length ? focusZones : zonesRaw.slice(0, 5)).map((z) =>
    interpretZone(z, type, isDataQuality)
  );

  const whatIsAffected: string[] = [];
  if (assets.length) {
    whatIsAffected.push(`Failed / stressed assets: ${assetLabel(assets)}`);
  }
  if (result.lost_source_kinds?.includes("hazard")) {
    whatIsAffected.push("Weather / hazard information (removed for this drill)");
  }
  if (result.lost_source_kinds?.includes("infrastructure")) {
    whatIsAffected.push("Facility / infrastructure records (suppressed for this drill)");
  }
  const totals = result.impact_totals;
  if (totals?.communities_worsened) {
    whatIsAffected.push(
      `${totals.communities_worsened} communities with worsened simulated vulnerability`
    );
  }
  if (totals?.communities_with_confidence_drop) {
    whatIsAffected.push(
      `${totals.communities_with_confidence_drop} communities with lower assessment confidence`
    );
  }
  if (totals?.communities_directly_linked_to_failed_assets) {
    whatIsAffected.push(
      `${totals.communities_directly_linked_to_failed_assets} communities linked to failed assets (≈2 km)`
    );
  }
  if (!whatIsAffected.length) {
    whatIsAffected.push(
      "No clear asset or community impact detected in this city's current data."
    );
  }

  let whyItMatters = "";
  if (type === "weather_source_loss") {
    whyItMatters =
      "Without verified weather/hazard inputs, officers may under- or over-prioritize communities. The correct response is to restore information — not to treat missing data as a flood.";
  } else if (type === "infrastructure_source_loss") {
    whyItMatters =
      "Access-based rankings depend on facility locations. Missing records make priorities incomplete until the registry is checked.";
  } else if (type === "bus_service_disruption") {
    whyItMatters = result.selected_route
      ? "Communities near the selected bus route may face harder access to services if that service stops. Treat route details from demo data as practice inputs, not official schedules."
      : "Without a stored bus route, we cannot map a real transit impact — only disclose that route data is missing.";
  } else if (type === "power_failure") {
    whyItMatters = result.selected_power_asset
      ? "Communities and facilities near the selected power asset may face simulated operational stress. This is not a verified outage map of the electrical grid."
      : "Without a stored power asset, results stay illustrative — do not treat them as a confirmed blackout footprint.";
  } else if (type === "multi_failure") {
    whyItMatters =
      "When roads and healthcare fail together, the same communities can face both travel and care pressure — coordination matters more than single-sector checks.";
  } else if (type === "hospital_outage") {
    whyItMatters =
      "Communities near the simulated outage may show higher travel-burden scores. That flags where to verify care access — not a confirmed patient impact count.";
  } else {
    whyItMatters =
      "Road access changes can raise disruption scores for nearby communities and delay reach to essential services until alternatives are confirmed.";
  }

  const whatNeedsVerification: string[] = [];
  if (assets.length) {
    whatNeedsVerification.push(`Status of: ${assetLabel(assets)}`);
  }
  if (isDataQuality) {
    whatNeedsVerification.push(
      type === "weather_source_loss"
        ? "Official weather / hazard bulletin for this city"
        : "Hospital, clinic, and road facility registry completeness"
    );
  }
  for (const z of zones.slice(0, 3)) {
    whatNeedsVerification.push(`${z.title} — field check of access and services`);
  }
  if (result.illustrative) {
    whatNeedsVerification.push(
      "Whether any real disruption exists — this run used illustrative assumptions"
    );
  }

  const whatHappensNext = [
    "Review the highlighted communities on the map (same city only).",
    "Create verification tasks for the highest-priority actions.",
    "Re-run the simulation after updating city data or confirming asset status.",
    "Do not treat this simulation as an operational forecast or dispatch order.",
  ];

  const actions = buildActions(result, zones, isDataQuality);
  const primaryNextStep =
    actions.find((a) => a.verificationStatus === "needs_field_check")?.action ||
    actions[0]?.action ||
    "Review the affected communities on the map, then verify the highest-priority item in the field.";

  const routeCtx =
    type === "bus_service_disruption" && result.selected_route
      ? `${result.selected_route.route_number || result.selected_route.name}${
          result.selected_route.is_synthetic ? " [demo]" : ""
        }`
      : type === "power_failure" && result.selected_power_asset
        ? `${result.selected_power_asset.name}${
            result.selected_power_asset.is_synthetic ? " [demo]" : ""
          }`
        : assetLabel(assets);

  if (result.selected_route) {
    whatIsAffected.unshift(
      `Bus route ${result.selected_route.route_number || result.selected_route.name}` +
        (result.selected_route.origin && result.selected_route.destination
          ? ` (${result.selected_route.origin} → ${result.selected_route.destination})`
          : "") +
        (result.selected_route.is_synthetic ? " — demo data" : "")
    );
  }
  if (result.selected_power_asset) {
    whatIsAffected.unshift(
      `Power asset: ${result.selected_power_asset.name}` +
        (result.selected_power_asset.is_synthetic ? " — demo data" : "")
    );
  }

  return {
    scenarioType: type,
    whatHappened: meta.oneLiner(routeCtx),
    howSerious: severity.level,
    severityExplanation: severity.explanation,
    severityProvisional: severity.provisional,
    whatIsAffected,
    whyItMatters,
    whatShouldWeDo: actions.slice(0, 4).map((a) => a.action),
    whatNeedsVerification,
    whatHappensNext,
    assumptionsDisclosed: result.assumptions || [],
    dataGaps: result.data_gaps || [],
    illustrative: Boolean(result.illustrative),
    isDataQualityScenario: isDataQuality,
    zones,
    actions,
    failedAssets: assets,
    selectedRoute: result.selected_route ?? null,
    selectedPowerAsset: result.selected_power_asset ?? null,
    cityId: result.city_id ?? null,
    scenarioId: result.scenario_id ?? null,
    scoreScaleNote:
      result.score_scale?.note ||
      "Multi-factor vulnerability score 0–100; higher is more concerning. Categories: low <25, moderate <50, high <75, critical ≥75.",
    primaryNextStep,
  };
}

export const SEVERITY_STYLES: Record<
  CascadeSeverity,
  { label: string; className: string; mapColor: string }
> = {
  low: {
    label: "Low impact",
    className: "border-teal-300 bg-teal-50 text-teal-900",
    mapColor: "#2dd4bf",
  },
  moderate: {
    label: "Moderate impact",
    className: "border-amber-300 bg-amber-50 text-amber-950",
    mapColor: "#fbbf24",
  },
  high: {
    label: "High impact",
    className: "border-orange-300 bg-orange-50 text-orange-950",
    mapColor: "#fb923c",
  },
  critical: {
    label: "Critical impact",
    className: "border-rose-300 bg-rose-50 text-rose-950",
    mapColor: "#f43f5e",
  },
  unknown: {
    label: "Unknown / insufficient information",
    className: "border-slate-300 bg-slate-100 text-slate-800",
    mapColor: "#94a3b8",
  },
};

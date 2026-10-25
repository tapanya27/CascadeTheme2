/** Risk category presentation — never color alone; always pair with label/icon. */

export type RiskCategory = "low" | "moderate" | "high" | "critical" | string;

export function categoryLabel(category: string | null | undefined): string {
  if (!category) return "Not scored yet";
  const map: Record<string, string> = {
    low: "Lower concern",
    moderate: "Needs checking",
    high: "Needs more attention",
    critical: "Highest priority for review",
  };
  return map[category] ?? category;
}

/** Fill colors for map polygons (hex for Leaflet) — teal → amber → coral → crimson. */
export function categoryFill(category: string | null | undefined): string {
  switch (category) {
    case "low":
      return "#2dd4bf";
    case "moderate":
      return "#fbbf24";
    case "high":
      return "#fb923c";
    case "critical":
      return "#f43f5e";
    default:
      return "#64748b";
  }
}

export function categoryBadgeClass(category: string | null | undefined): string {
  switch (category) {
    case "low":
      return "border-teal-200 bg-teal-50 text-teal-800";
    case "moderate":
      return "border-amber-200 bg-amber-50 text-amber-900";
    case "high":
      return "border-orange-200 bg-orange-50 text-orange-900";
    case "critical":
      return "border-rose-200 bg-rose-50 text-rose-900";
    default:
      return "border-border bg-secondary text-secondary-foreground";
  }
}

/** Plain-language factor labels for score components. */
export function friendlyFactorLabel(keyOrLabel: string): string {
  const map: Record<string, string> = {
    flood_hazard_exposure: "Heavy rainfall / flood markers",
    population_exposure: "People potentially affected",
    road_disruption_risk: "Limited road connectivity",
    healthcare_travel_burden: "Distance from essential healthcare",
    infrastructure_availability: "Nearby essential services",
  };
  return map[keyOrLabel] ?? keyOrLabel;
}

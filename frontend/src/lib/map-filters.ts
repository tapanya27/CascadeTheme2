/** Pure helpers for map zone filtering (unit-tested). */

export type ZoneMapProperties = {
  id: string;
  code: string;
  name: string;
  is_synthetic?: boolean;
  overall_score?: number | null;
  category?: string | null;
  confidence?: number | null;
  top_factors?: string[];
  data_quality?: Record<string, unknown>;
  data_source?: string | null;
  scoring_version?: string | null;
};

export type ZoneFilter = {
  categories: string[]; // empty = all
  scoreMin: number;
  scoreMax: number;
  includeUnscored: boolean;
};

export const DEFAULT_ZONE_FILTER: ZoneFilter = {
  categories: [],
  scoreMin: 0,
  scoreMax: 100,
  includeUnscored: true,
};

export function matchesZoneFilter(
  props: ZoneMapProperties,
  filter: ZoneFilter
): boolean {
  const score = props.overall_score;
  const category = props.category;

  if (score == null || category == null) {
    return filter.includeUnscored;
  }
  if (score < filter.scoreMin || score > filter.scoreMax) {
    return false;
  }
  if (filter.categories.length > 0 && !filter.categories.includes(category)) {
    return false;
  }
  return true;
}

export function filterFeatures<T extends { properties?: ZoneMapProperties | null }>(
  features: T[],
  filter: ZoneFilter
): T[] {
  return features.filter((f) => {
    const props = f.properties;
    if (!props) return false;
    return matchesZoneFilter(props, filter);
  });
}

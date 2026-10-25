import { describe, expect, it } from "vitest";

import {
  DEFAULT_ZONE_FILTER,
  filterFeatures,
  matchesZoneFilter,
} from "@/lib/map-filters";

describe("matchesZoneFilter", () => {
  it("includes unscored when allowed", () => {
    expect(
      matchesZoneFilter(
        { id: "1", code: "A", name: "A" },
        { ...DEFAULT_ZONE_FILTER, includeUnscored: true }
      )
    ).toBe(true);
  });

  it("excludes unscored when disabled", () => {
    expect(
      matchesZoneFilter(
        { id: "1", code: "A", name: "A" },
        { ...DEFAULT_ZONE_FILTER, includeUnscored: false }
      )
    ).toBe(false);
  });

  it("filters by category and score range", () => {
    const props = {
      id: "1",
      code: "A",
      name: "A",
      overall_score: 62,
      category: "high",
    };
    expect(
      matchesZoneFilter(props, {
        categories: ["high"],
        scoreMin: 50,
        scoreMax: 100,
        includeUnscored: false,
      })
    ).toBe(true);
    expect(
      matchesZoneFilter(props, {
        categories: ["low"],
        scoreMin: 50,
        scoreMax: 100,
        includeUnscored: false,
      })
    ).toBe(false);
    expect(
      matchesZoneFilter(props, {
        categories: [],
        scoreMin: 70,
        scoreMax: 100,
        includeUnscored: false,
      })
    ).toBe(false);
  });
});

describe("filterFeatures", () => {
  it("filters feature collections by properties", () => {
    const features = [
      {
        properties: {
          id: "1",
          code: "A",
          name: "A",
          overall_score: 20,
          category: "low",
        },
      },
      {
        properties: {
          id: "2",
          code: "B",
          name: "B",
          overall_score: 80,
          category: "critical",
        },
      },
    ];
    const out = filterFeatures(features, {
      categories: ["critical"],
      scoreMin: 0,
      scoreMax: 100,
      includeUnscored: false,
    });
    expect(out).toHaveLength(1);
    expect(out[0].properties?.id).toBe("2");
  });
});

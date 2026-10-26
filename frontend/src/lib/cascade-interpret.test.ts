import { describe, expect, it } from "vitest";

import { interpretCascade, overallSeverity, type CascadeResult } from "./cascade-interpret";

function baseResult(over: Partial<CascadeResult>): CascadeResult {
  return {
    scenario_id: "sim-1",
    city_id: "guwahati",
    scenario_type: "road_closure",
    failed_assets: [
      {
        id: "r1",
        name: "NH Bypass",
        infrastructure_type: "road",
        city_id: "guwahati",
      },
    ],
    lost_source_kinds: [],
    data_gaps: [],
    zone_impacts: [
      {
        zone_id: "z1",
        zone_code: "GUW-203",
        zone_name: "Dispur Ward Sample",
        display_name: "Dispur Ward Sample",
        baseline_multifactor_score: 30,
        scenario_multifactor_score: 42,
        delta_multifactor_score: 12,
        score_direction: "worsened",
        higher_is_worse: true,
        baseline_category: "moderate",
        scenario_category: "moderate",
        failed_affecting_zone: true,
        service_effects: ["road_access_worsened"],
      },
    ],
    impact_totals: {
      communities_checked: 10,
      communities_with_change: 1,
      communities_worsened: 1,
      communities_with_confidence_drop: 0,
      communities_directly_linked_to_failed_assets: 1,
    },
    assumptions: ["test assumption"],
    ...over,
  };
}

describe("interpretCascade", () => {
  it("explains road closure with community names, not bare IDs", () => {
    const out = interpretCascade(baseResult({}));
    expect(out.whatHappened).toMatch(/road/i);
    expect(out.zones[0].title).toBe("Dispur Ward Sample");
    expect(out.zones[0].zoneCode).toBe("GUW-203");
    expect(out.whatShouldWeDo.length).toBeGreaterThan(0);
    expect(out.actions.some((a) => /road/i.test(a.action))).toBe(true);
  });

  it("treats weather source loss as data quality, not a flood disaster", () => {
    const out = interpretCascade(
      baseResult({
        scenario_type: "weather_source_loss",
        failed_assets: [],
        lost_source_kinds: ["hazard"],
        zone_impacts: [
          {
            zone_id: "z1",
            zone_code: "GUW-203",
            zone_name: null,
            display_name: "Community GUW-203",
            name_unavailable: true,
            baseline_multifactor_score: 40,
            scenario_multifactor_score: 40,
            delta_multifactor_score: 0,
            score_direction: "unchanged",
            baseline_confidence: 0.7,
            scenario_confidence: 0.4,
            service_effects: ["hazard_data_unavailable"],
            flood_notes: "does not mean a flood occurred",
          },
        ],
        impact_totals: {
          communities_checked: 5,
          communities_worsened: 0,
          communities_with_confidence_drop: 5,
          communities_directly_linked_to_failed_assets: 0,
        },
      })
    );
    expect(out.isDataQualityScenario).toBe(true);
    expect(out.whatHappened.toLowerCase()).toContain("does not mean a flood");
    expect(out.whyItMatters.toLowerCase()).not.toContain("flooding is occurring");
    expect(out.zones[0].title).toContain("Community GUW-203");
    expect(out.zones[0].explanation.toLowerCase()).toContain("not evidence that flooding");
  });

  it("keeps bus and power scenarios distinct", () => {
    const bus = interpretCascade(
      baseResult({
        scenario_type: "bus_service_disruption",
        selected_route: {
          id: "b1",
          name: "Demo Bus NAG-101",
          route_number: "NAG-101",
          origin: "A",
          destination: "B",
          stops: ["A", "B"],
          is_synthetic: true,
        },
        failed_assets: [
          {
            id: "b1",
            name: "Demo Bus NAG-101",
            infrastructure_type: "bus_route",
            is_synthetic: true,
          },
        ],
      })
    );
    const power = interpretCascade(
      baseResult({
        scenario_type: "power_failure",
        illustrative: true,
        failed_assets: [],
        selected_power_asset: null,
        data_gaps: ["No power-asset records"],
        zone_impacts: [
          {
            zone_id: "z2",
            zone_code: "NAG-001",
            zone_name: "Civil Lines",
            delta_multifactor_score: 2,
            score_direction: "worsened",
            service_effects: ["illustrative_service_availability_drop"],
          },
        ],
      })
    );
    expect(bus.whatHappened.toLowerCase()).toContain("bus");
    expect(bus.selectedRoute?.route_number).toBe("NAG-101");
    expect(power.whatHappened.toLowerCase()).toMatch(/power|illustrative/);
    expect(power.whatHappened.toLowerCase()).not.toContain("bus-service");
    expect(bus.whatHappened).not.toEqual(power.whatHappened);
  });

  it("does not assign critical severity only because a score changed slightly", () => {
    const sev = overallSeverity(
      baseResult({
        zone_impacts: [
          {
            zone_id: "z1",
            delta_multifactor_score: 0.2,
            score_direction: "worsened",
            scenario_category: "low",
          },
        ],
        impact_totals: {
          communities_worsened: 1,
          communities_directly_linked_to_failed_assets: 0,
        },
      }),
      false
    );
    expect(sev.level).not.toBe("critical");
  });

  it("hospital and multi-failure produce distinct narratives", () => {
    const hosp = interpretCascade(
      baseResult({
        scenario_type: "hospital_outage",
        failed_assets: [
          {
            id: "h1",
            name: "City Civil Hospital",
            infrastructure_type: "hospital",
          },
        ],
      })
    );
    const multi = interpretCascade(
      baseResult({
        scenario_type: "multi_failure",
        failed_assets: [
          { id: "r1", name: "Ring Road", infrastructure_type: "road" },
          {
            id: "h1",
            name: "City Civil Hospital",
            infrastructure_type: "hospital",
          },
        ],
      })
    );
    expect(hosp.whatHappened.toLowerCase()).toContain("hospital");
    expect(multi.whyItMatters.toLowerCase()).toMatch(/together|combined/);
    expect(hosp.whatHappened).not.toEqual(multi.whatHappened);
  });
});

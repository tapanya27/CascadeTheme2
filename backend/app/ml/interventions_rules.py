"""Rule-based intervention recommendations linked to scored features.

Actionable and explainable. Never claims optimality or exact deployment orders.
"""

from __future__ import annotations

from typing import Any, Optional


def recommend_interventions(row: dict[str, Any]) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []

    def add(
        issue: str,
        action: str,
        *,
        evidence: str,
        priority: str,
        feature: Optional[str] = None,
    ) -> None:
        recs.append(
            {
                "issue": issue,
                "recommended_action": action,
                "evidence": evidence,
                "priority": priority,
                "feature": feature,
                "optimality_claim": False,
                "note": (
                    "Evidence-linked suggestion for assessment prioritization — "
                    "not a proven optimal intervention plan."
                ),
            }
        )

    hosp = row.get("nearest_hospital_km")
    if hosp is not None:
        try:
            if float(hosp) >= 5.0:
                add(
                    "Long hospital access distance",
                    "Prioritize access-route and emergency-transport assessment for this zone.",
                    evidence=f"nearest_hospital_km={float(hosp):.2f} (great-circle, not network ETA)",
                    priority="high" if float(hosp) >= 8 else "medium",
                    feature="nearest_hospital_km",
                )
        except (TypeError, ValueError):
            pass

    road_c = row.get("road_connectivity")
    if road_c is not None:
        try:
            if float(road_c) <= 0.25:
                add(
                    "Low road connectivity signal",
                    "Inspect alternative evacuation / access routes and OSM coverage gaps.",
                    evidence=f"road_connectivity={float(road_c):.3f} (OSM-derived proxy)",
                    priority="high",
                    feature="road_connectivity",
                )
        except (TypeError, ValueError):
            pass

    transit = row.get("transit_accessibility")
    if transit is not None:
        try:
            if float(transit) <= 0:
                add(
                    "No mapped transit stops in zone sample",
                    "Prioritize transit resilience and last-mile access review.",
                    evidence="transit_accessibility=0 in OSM sample (may be incomplete)",
                    priority="medium",
                    feature="transit_accessibility",
                )
        except (TypeError, ValueError):
            pass

    rain72 = row.get("rainfall_72h_mm")
    if rain72 is not None:
        try:
            if float(rain72) >= 40:
                add(
                    "Elevated recent precipitation (city-centroid estimate)",
                    "Review drainage hotspots and flood-proxy monitoring for this city/zone set.",
                    evidence=f"rainfall_72h_mm={float(rain72):.1f} from Open-Meteo city centroid",
                    priority="high" if float(rain72) >= 80 else "medium",
                    feature="rainfall_72h_mm",
                )
        except (TypeError, ValueError):
            pass

    fac = row.get("facility_count")
    if fac is not None:
        try:
            if float(fac) <= 0 and (hosp is None or float(hosp) >= 3):
                add(
                    "No healthcare facilities intersecting zone",
                    "Assess temporary resource placement options under explicit scenario assumptions.",
                    evidence="facility_count=0 in zone OSM sample",
                    priority="medium",
                    feature="facility_count",
                )
        except (TypeError, ValueError):
            pass

    if row.get("anomaly_flag"):
        add(
            "Unusual infrastructure/exposure combination",
            "Human review of feature mix; verify data quality before operational use.",
            evidence=f"isolation_forest anomaly_score={row.get('anomaly_score')}",
            priority="medium",
            feature="anomaly_flag",
        )

    if row.get("data_quality_flag") == "low":
        add(
            "Low source coverage",
            "Improve OSM/weather/population data coverage before high-stakes decisions.",
            evidence=f"source_coverage_score={row.get('source_coverage_score')}",
            priority="high",
            feature="source_coverage_score",
        )

    if not recs:
        add(
            "No high-priority rule fired",
            "Continue routine monitoring; re-run when OSM/weather coverage improves.",
            evidence="Heuristic rules found no threshold breach",
            priority="low",
        )
    return recs

"""Community Risk & Impact analysis — spatial impact assessment around alerts.

Given an alert (or arbitrary point + radius), find affected communities using
PostGIS spatial queries, enrich with existing vulnerability scores,
infrastructure, dependency relationships, and produce an officer-ready
impact assessment.

Honesty rules:
- Impact radius is a geometric approximation, not a calibrated damage model.
- Severity levels are derived from existing vulnerability scores, not new predictions.
- Demo/synthetic data sources are explicitly labeled in every affected community.
- Missing data is never invented.
- Dependency pathways reflect analytical model assumptions, not proven causal certainty.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cities.registry import require_city
from app.models.alert import LiveAlert
from app.models.infrastructure import Infrastructure, InfrastructureType
from app.models.zone import Zone
from app.repositories.assessments import AssessmentRepository
from app.services.dependency_graph import DEFAULT_EDGES

logger = logging.getLogger(__name__)

# Default impact radius in meters — geometric buffer, not a calibrated model.
DEFAULT_IMPACT_RADIUS_M = 3000
MAX_IMPACT_RADIUS_M = 10000

# Severity thresholds based on existing vulnerability scores (0–100).
SEVERITY_THRESHOLDS = {
    "critical": 70,
    "high": 55,
    "moderate": 35,
    "low": 0,
}

# Alert-type to impact-type mapping for contextual recommendations & dependency pathways.
ALERT_IMPACT_CONTEXT: dict[str, dict[str, Any]] = {
    "weather_rainfall": {
        "primary_concern": "Flood exposure and drainage overload",
        "infrastructure_focus": ["road", "hospital", "clinic", "drainage"],
        "recommended_radius_m": 3000,
        "impact_factors": [
            "Low-lying areas may experience waterlogging and storm drain overflow",
            "Road access to healthcare facilities may be disrupted",
            "Communities with high baseline fragility and weak drainage face highest disruption",
        ],
        "dependency_pathway": [
            {"source": "heavy_rainfall", "target": "flood_exposure", "relation": "may increase"},
            {"source": "flood_exposure", "target": "road_disruption", "relation": "may cause"},
            {"source": "road_disruption", "target": "hospital_travel_time", "relation": "may increase"},
            {"source": "hospital_travel_time", "target": "healthcare_accessibility", "relation": "may reduce"},
        ],
        "cascading_mechanism": (
            "Rainfall accumulation may trigger localized inundation, impeding road transit "
            "and lengthening emergency response times to nearby clinical infrastructure."
        ),
    },
    "flood_warning": {
        "primary_concern": "Inundation, access cutoff, and evacuation barriers",
        "infrastructure_focus": ["road", "hospital", "clinic", "emergency_facility"],
        "recommended_radius_m": 5000,
        "impact_factors": [
            "Immediate flood risk to low-elevation communities",
            "Evacuation and transit routes may be submerged or compromised",
            "Emergency services and primary health clinic access may be severed",
        ],
        "dependency_pathway": [
            {"source": "flood_exposure", "target": "road_disruption", "relation": "may cause"},
            {"source": "road_disruption", "target": "hospital_travel_time", "relation": "may increase"},
            {"source": "hospital_travel_time", "target": "healthcare_accessibility", "relation": "may reduce"},
            {"source": "infrastructure_availability", "target": "healthcare_accessibility", "relation": "strained by"},
        ],
        "cascading_mechanism": (
            "Rising floodwaters directly block primary road arteries, cutting off surrounding fragile "
            "communities from emergency healthcare centers and essential support services."
        ),
    },
    "road_closure": {
        "primary_concern": "Direct transit disruption and isolation",
        "infrastructure_focus": ["road", "hospital", "clinic"],
        "recommended_radius_m": 2500,
        "impact_factors": [
            "Communities dependent on this corridor lose direct transportation access",
            "Healthcare travel burden escalates sharply for adjoining zones",
            "Bottlenecks and congestion may cascade into secondary access routes",
        ],
        "dependency_pathway": [
            {"source": "road_disruption", "target": "hospital_travel_time", "relation": "may increase"},
            {"source": "hospital_travel_time", "target": "healthcare_accessibility", "relation": "may reduce"},
        ],
        "cascading_mechanism": (
            "Segment closure forces detours onto lower-capacity roads, compounding travel times "
            "for ambulances, supply deliveries, and vulnerable residents requiring ongoing care."
        ),
    },
    "infrastructure": {
        "primary_concern": "Critical utility or health facility failure",
        "infrastructure_focus": ["hospital", "clinic", "emergency_facility", "power_asset"],
        "recommended_radius_m": 3500,
        "impact_factors": [
            "Loss of service or reduced operational throughput at primary facility",
            "Surrounding settlements face sudden service deficits",
            "Nearby alternate facilities absorb redirected patient or service loads",
        ],
        "dependency_pathway": [
            {"source": "infrastructure_availability", "target": "healthcare_accessibility", "relation": "may reduce"},
            {"source": "road_disruption", "target": "infrastructure_availability", "relation": "impedes maintenance"},
        ],
        "cascading_mechanism": (
            "Service outages at essential nodes ripple outward, shifting emergency burden onto "
            "subordinate community clinics that may lack reserve equipment or emergency power."
        ),
    },
    "community_report": {
        "primary_concern": "Ground-level verified disturbance or localized hazard",
        "infrastructure_focus": ["road", "hospital", "clinic"],
        "recommended_radius_m": 2000,
        "impact_factors": [
            "Reported conditions directly affect adjacent residential wards",
            "Field verification required before heavy resource deployment",
            "Potential precursor indicator for broader neighborhood vulnerability",
        ],
        "dependency_pathway": [
            {"source": "community_hazard", "target": "local_vulnerability", "relation": "observed impact"},
            {"source": "road_disruption", "target": "healthcare_accessibility", "relation": "potential obstacle"},
        ],
        "cascading_mechanism": (
            "Localized community stress reports often indicate early drainage or access failures "
            "that precede system-level disruptions if rainfall or runoff continues."
        ),
    },
    "risk_change": {
        "primary_concern": "Vulnerability shift and baseline risk elevation",
        "infrastructure_focus": ["road", "hospital", "clinic"],
        "recommended_radius_m": 3000,
        "impact_factors": [
            "Updated analytical models flag increased vulnerability indices",
            "Adjacent communities may undergo comparable socio-spatial shifts",
            "Re-prioritization of preventive inspections is indicated",
        ],
        "dependency_pathway": [
            {"source": "model_indicators", "target": "vulnerability_score", "relation": "updated ranking"},
            {"source": "healthcare_accessibility", "target": "community_resilience", "relation": "core determinant"},
        ],
        "cascading_mechanism": (
            "Elevated vulnerability calculations indicate reduced absorption capacity; even minor "
            "subsequent weather events will cause larger community disruptions."
        ),
    },
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _impact_severity(score: Optional[float]) -> str:
    """Derive impact severity from existing vulnerability score."""
    if score is None:
        return "unknown"
    for level, threshold in SEVERITY_THRESHOLDS.items():
        if score >= threshold:
            return level
    return "low"


def _impact_color(severity: str) -> str:
    """Map severity to display color for the frontend."""
    return {
        "critical": "#ef4444",
        "high": "#f97316",
        "moderate": "#eab308",
        "low": "#22c55e",
        "unknown": "#6b7280",
    }.get(severity, "#6b7280")


def _extract_components_and_factors(latest: Any) -> tuple[list[str], list[str], str]:
    """Safely extract top vulnerability factors, reasons, and explanation."""
    factors: list[str] = []
    reasons: list[str] = []
    explanation = ""

    if not latest:
        return factors, reasons, explanation

    explanation = getattr(latest, "explanation", "") or ""

    raw_reasons = getattr(latest, "reasons", None)
    if raw_reasons:
        if isinstance(raw_reasons, str):
            try:
                raw_reasons = json.loads(raw_reasons)
            except Exception:
                raw_reasons = [raw_reasons]
        if isinstance(raw_reasons, list):
            reasons = [str(r) for r in raw_reasons if r]

    raw_components = getattr(latest, "components", None)
    if raw_components:
        if isinstance(raw_components, str):
            try:
                raw_components = json.loads(raw_components)
            except Exception:
                raw_components = []
        if isinstance(raw_components, list):
            valid_comps = [c for c in raw_components if isinstance(c, dict) and c.get("contribution") is not None]
            sorted_comps = sorted(
                valid_comps,
                key=lambda c: abs(c.get("contribution", 0)),
                reverse=True,
            )
            for comp in sorted_comps[:4]:
                label = comp.get("label") or comp.get("key") or "Factor"
                contrib = comp.get("contribution", 0.0)
                reason_txt = comp.get("reason")
                if reason_txt:
                    factors.append(f"{label} ({contrib:+.1f} pts): {reason_txt}")
                else:
                    factors.append(f"{label}: contributes {contrib:+.1f} pts")

    return factors, reasons, explanation


def _generate_recommendations(
    alert_type: str,
    affected_communities: list[dict[str, Any]],
    affected_infra: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Generate context-aware recommendations based on alert type and affected areas."""
    recs: list[dict[str, str]] = []
    critical_count = sum(1 for c in affected_communities if c.get("impact_severity") == "critical")
    high_count = sum(1 for c in affected_communities if c.get("impact_severity") == "high")
    hospitals_nearby = [i for i in affected_infra if i.get("kind") in ("hospital", "clinic")]

    if critical_count > 0:
        names = ", ".join(c["zone_name"] for c in affected_communities if c.get("impact_severity") == "critical")[:60]
        recs.append({
            "priority": "urgent",
            "action": f"Prioritize rapid field check for {critical_count} critical community(ies): {names}",
            "reason": (
                "These communities exhibit high baseline vulnerability scores in the analytical model. "
                "Any secondary disruption could create severe compounding hardships."
            ),
        })

    if high_count > 0:
        recs.append({
            "priority": "high",
            "action": f"Alert ward officers in {high_count} high-severity zone(s) to monitor access points",
            "reason": "Elevated vulnerability indices mean reduced capacity to handle prolonged service delays.",
        })

    if hospitals_nearby:
        names = ", ".join(h["name"] for h in hospitals_nearby[:3])
        recs.append({
            "priority": "high",
            "action": f"Verify ambulance & emergency corridor connectivity to healthcare assets: {names}",
            "reason": "Hospital proximity is vital; road disruptions between communities and these facilities escalate risk.",
        })

    context = ALERT_IMPACT_CONTEXT.get(alert_type, ALERT_IMPACT_CONTEXT["community_report"])
    recs.append({
        "priority": "medium",
        "action": f"Operational focus: {context['primary_concern']}",
        "reason": context["cascading_mechanism"],
    })

    if any(c.get("is_synthetic") for c in affected_communities):
        recs.append({
            "priority": "info",
            "action": "Flag demo/synthetic baselines to operational team",
            "reason": (
                "Certain affected zones utilize synthetic proxy datasets. Validate actual on-the-ground conditions "
                "with local ward contacts before committing heavy resources."
            ),
        })

    return recs


def analyze_alert_impact(
    db: Session,
    *,
    alert_id: Optional[UUID | str] = None,
    city_id: str,
    lon: Optional[float] = None,
    lat: Optional[float] = None,
    radius_m: Optional[float] = None,
    alert_type: Optional[str] = None,
) -> dict[str, Any]:
    """
    Analyze community risk and impact around an alert or point.

    Uses PostGIS ST_DWithin and ST_Distance queries against city-specific zones
    and infrastructure, enriched with vulnerability assessments and dependency pathways.
    """
    city = require_city(city_id)
    alert_data: Optional[dict[str, Any]] = None

    if alert_id is not None:
        if isinstance(alert_id, str):
            try:
                alert_id = UUID(alert_id)
            except ValueError:
                return {"error": "Invalid alert_id UUID", "city_id": city_id}

        alert_row = (
            db.query(LiveAlert)
            .filter(LiveAlert.id == alert_id, LiveAlert.city_id == city_id)
            .one_or_none()
        )
        if alert_row is None:
            return {
                "error": f"Alert {alert_id} not found for city '{city_id}'",
                "city_id": city_id,
            }
        lon = alert_row.lon
        lat = alert_row.lat
        alert_type = alert_row.alert_type
        alert_data = {
            "id": str(alert_row.id),
            "title": alert_row.title,
            "alert_type": alert_row.alert_type,
            "severity": alert_row.severity,
            "is_demo": bool(alert_row.is_demo),
            "authenticity": alert_row.authenticity,
            "area_label": alert_row.area_label,
            "description": alert_row.description,
            "observed_at": alert_row.observed_at.isoformat() if alert_row.observed_at else None,
            "lon": alert_row.lon,
            "lat": alert_row.lat,
        }

    if lon is None or lat is None:
        # Fall back to city centroid
        clon, clat = city.centroid
        lon = clon
        lat = clat
        has_coords = False
    else:
        has_coords = True

    context = ALERT_IMPACT_CONTEXT.get(
        alert_type or "community_report",
        ALERT_IMPACT_CONTEXT["community_report"],
    )
    effective_radius = min(
        float(radius_m or context["recommended_radius_m"]),
        float(MAX_IMPACT_RADIUS_M),
    )

    # 1. Spatial query: affected communities (zones) within radius
    zone_sql = text("""
        SELECT
            z.id::text                             AS zone_id,
            z.code                                 AS zone_code,
            z.name                                 AS zone_name,
            z.city_id                              AS city_id,
            ST_Distance(
                z.boundary::geography,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
            )                                      AS distance_m,
            ST_X(ST_Centroid(z.boundary))           AS centroid_lon,
            ST_Y(ST_Centroid(z.boundary))           AS centroid_lat,
            ST_AsGeoJSON(z.boundary)::text          AS boundary_geojson,
            ds.is_synthetic                         AS is_synthetic,
            ds.name                                 AS data_source_name
        FROM zones z
        JOIN data_sources ds ON z.data_source_id = ds.id
        WHERE z.city_id = :city_id
          AND ST_DWithin(
                z.boundary::geography,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                :radius_m
              )
        ORDER BY distance_m ASC
    """)
    zone_rows = db.execute(zone_sql, {
        "lon": lon,
        "lat": lat,
        "city_id": city_id,
        "radius_m": effective_radius,
    }).fetchall()

    arepo = AssessmentRepository(db)
    affected_communities: list[dict[str, Any]] = []

    for row in zone_rows:
        zone_uuid = UUID(row.zone_id)
        latest = arepo.latest_for_zone(zone_uuid)

        score = latest.overall_score if latest else None
        category = latest.category if latest else None
        confidence = latest.confidence if latest else None

        factors, reasons, explanation = _extract_components_and_factors(latest)
        severity = _impact_severity(score)
        dist_km = round(row.distance_m / 1000.0, 2) if row.distance_m is not None else 0.0

        community = {
            "zone_id": row.zone_id,
            "zone_code": row.zone_code,
            "zone_name": row.zone_name,
            "distance_m": round(row.distance_m, 1) if row.distance_m is not None else 0.0,
            "distance_km": dist_km,
            "centroid": {"lon": row.centroid_lon, "lat": row.centroid_lat},
            "boundary_geojson": json.loads(row.boundary_geojson) if row.boundary_geojson else None,
            "vulnerability_score": round(score, 1) if score is not None else None,
            "vulnerability_category": category or "Unscored",
            "impact_severity": severity,
            "impact_color": _impact_color(severity),
            "confidence": round(confidence, 2) if confidence is not None else None,
            "is_synthetic": bool(row.is_synthetic),
            "data_source_name": row.data_source_name,
            "top_vulnerability_factors": factors,
            "reasons": reasons,
            "explanation": explanation,
            "assessment_available": latest is not None,
            "hazard_only_score": (
                round(latest.hazard_only_score, 1)
                if latest and getattr(latest, "hazard_only_score", None) is not None
                else None
            ),
            "hazard_only_rank": getattr(latest, "hazard_only_rank", None) if latest else None,
            "multifactor_rank": getattr(latest, "multifactor_rank", None) if latest else None,
            "rank_uplift": getattr(latest, "rank_uplift", None) if latest else None,
        }
        affected_communities.append(community)

    # 2. Spatial query: affected infrastructure within radius
    infra_sql = text("""
        SELECT
            i.id::text                             AS infra_id,
            i.name                                 AS infra_name,
            i.infrastructure_type::text            AS infra_type,
            i.city_id                              AS city_id,
            ST_Distance(
                i.geometry::geography,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
            )                                      AS distance_m,
            ST_X(ST_Centroid(i.geometry))           AS centroid_lon,
            ST_Y(ST_Centroid(i.geometry))           AS centroid_lat,
            ds.is_synthetic                         AS is_synthetic,
            ds.name                                 AS data_source_name
        FROM infrastructure i
        JOIN data_sources ds ON i.data_source_id = ds.id
        WHERE i.city_id = :city_id
          AND ST_DWithin(
                i.geometry::geography,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                :radius_m
              )
        ORDER BY distance_m ASC
    """)
    infra_rows = db.execute(infra_sql, {
        "lon": lon,
        "lat": lat,
        "city_id": city_id,
        "radius_m": effective_radius,
    }).fetchall()

    affected_infra: list[dict[str, Any]] = []
    for row in infra_rows:
        affected_infra.append({
            "id": row.infra_id,
            "name": row.infra_name,
            "kind": row.infra_type,
            "distance_m": round(row.distance_m, 1) if row.distance_m is not None else 0.0,
            "distance_km": round(row.distance_m / 1000.0, 2) if row.distance_m is not None else 0.0,
            "centroid": {"lon": row.centroid_lon, "lat": row.centroid_lat},
            "is_synthetic": bool(row.is_synthetic),
            "data_source_name": row.data_source_name,
        })

    # 3. Summary metrics
    severity_counts: dict[str, int] = {
        "critical": 0,
        "high": 0,
        "moderate": 0,
        "low": 0,
        "unknown": 0,
    }
    for c in affected_communities:
        s = c["impact_severity"]
        severity_counts[s] = severity_counts.get(s, 0) + 1

    scores = [c["vulnerability_score"] for c in affected_communities if c["vulnerability_score"] is not None]
    max_score = max(scores) if scores else None
    avg_score = round(sum(scores) / len(scores), 1) if scores else None
    synthetic_count = sum(1 for c in affected_communities if c["is_synthetic"])

    # Determine overall impact severity
    overall_severity = "low"
    if severity_counts["critical"] > 0:
        overall_severity = "critical"
    elif severity_counts["high"] > 0:
        overall_severity = "high"
    elif severity_counts["moderate"] > 0:
        overall_severity = "moderate"
    elif len(affected_communities) == 0:
        overall_severity = "low"

    # 4. Generate recommendations
    recommendations = _generate_recommendations(
        alert_type or "community_report",
        affected_communities,
        affected_infra,
    )

    # 5. Build GeoJSON for the impact radius circle
    circle_points = 64
    impact_circle_coords: list[list[float]] = []
    for i in range(circle_points + 1):
        angle = (2 * math.pi * i) / circle_points
        dlat = (effective_radius / 111_320.0) * math.cos(angle)
        dlon = (effective_radius / (111_320.0 * math.cos(math.radians(lat)))) * math.sin(angle)
        impact_circle_coords.append([round(lon + dlon, 6), round(lat + dlat, 6)])

    impact_circle_geojson = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [impact_circle_coords],
        },
        "properties": {
            "kind": "impact_radius",
            "radius_m": effective_radius,
            "center_lon": lon,
            "center_lat": lat,
            "note": "Geometric buffer — not a calibrated damage or flood model.",
        },
    }

    # 6. FeatureCollection of affected community polygons for direct Leaflet rendering
    community_features = []
    for c in affected_communities:
        if c.get("boundary_geojson"):
            community_features.append({
                "type": "Feature",
                "id": c["zone_id"],
                "properties": {
                    "zone_id": c["zone_id"],
                    "zone_code": c["zone_code"],
                    "zone_name": c["zone_name"],
                    "distance_km": c["distance_km"],
                    "vulnerability_score": c["vulnerability_score"],
                    "impact_severity": c["impact_severity"],
                    "impact_color": c["impact_color"],
                    "is_synthetic": c["is_synthetic"],
                },
                "geometry": c["boundary_geojson"],
            })

    affected_zones_geojson = {
        "type": "FeatureCollection",
        "features": community_features,
    }

    return {
        "city_id": city_id,
        "city_name": city.name,
        "alert": alert_data,
        "analysis_point": {
            "lon": lon,
            "lat": lat,
            "has_coordinates": has_coords,
            "note": (
                "Alert coordinates used for spatial analysis."
                if has_coords
                else "No reliable coordinates — city centroid used as fallback. Results are illustrative only."
            ),
        },
        "impact_radius_m": effective_radius,
        "impact_context": {
            "primary_concern": context["primary_concern"],
            "infrastructure_focus": context["infrastructure_focus"],
            "impact_factors": context["impact_factors"],
            "dependency_pathway": context["dependency_pathway"],
            "cascading_mechanism": context["cascading_mechanism"],
        },
        "overall_severity": overall_severity,
        "overall_severity_color": _impact_color(overall_severity),
        "summary": {
            "total_communities_affected": len(affected_communities),
            "severity_breakdown": severity_counts,
            "max_vulnerability_score": max_score,
            "average_vulnerability_score": avg_score,
            "total_infrastructure_in_radius": len(affected_infra),
            "healthcare_facilities_in_radius": sum(
                1 for i in affected_infra if i["kind"] in ("hospital", "clinic")
            ),
            "roads_in_radius": sum(
                1 for i in affected_infra if i["kind"] == "road"
            ),
            "synthetic_data_count": synthetic_count,
        },
        "affected_communities": affected_communities,
        "affected_infrastructure": affected_infra,
        "affected_zones_geojson": affected_zones_geojson,
        "recommendations": recommendations,
        "impact_circle_geojson": impact_circle_geojson,
        "generated_at": _utcnow().isoformat(),
        "disclaimers": [
            "Impact radius is a geometric approximation — not a calibrated hydrological or structural damage model.",
            "Severity classifications reflect existing model vulnerability baselines, not guaranteed outcomes.",
            "This decision-support analysis must be combined with on-site verification before dispatch decisions.",
            *(
                [
                    f"{synthetic_count} of {len(affected_communities)} affected communities "
                    "rely on demo/synthetic data — treats outputs as illustrative."
                ]
                if synthetic_count > 0
                else []
            ),
            *(
                [
                    "Alert has no specific coordinate pin; city center was used as spatial fallback."
                ]
                if not has_coords
                else []
            ),
        ],
    }


def get_city_community_risk_overview(db: Session, city_id: str) -> dict[str, Any]:
    """
    Get full community risk & impact overview for all communities in a city.

    Allows officers to review every community's risk score, severity,
    vulnerabilities, component explanations, and active alert proximity.
    """
    city = require_city(city_id)

    # 1. Fetch all zones for the city with geometry centroids and data sources
    zone_sql = text("""
        SELECT
            z.id::text                             AS zone_id,
            z.code                                 AS zone_code,
            z.name                                 AS zone_name,
            z.city_id                              AS city_id,
            ST_X(ST_Centroid(z.boundary))           AS centroid_lon,
            ST_Y(ST_Centroid(z.boundary))           AS centroid_lat,
            ST_AsGeoJSON(z.boundary)::text          AS boundary_geojson,
            ds.is_synthetic                         AS is_synthetic,
            ds.name                                 AS data_source_name
        FROM zones z
        JOIN data_sources ds ON z.data_source_id = ds.id
        WHERE z.city_id = :city_id
        ORDER BY z.name ASC
    """)
    zone_rows = db.execute(zone_sql, {"city_id": city_id}).fetchall()

    # 2. Fetch active (unresolved) alerts for proximity checking
    alert_sql = text("""
        SELECT
            id::text      AS id,
            alert_type,
            severity,
            title,
            lon,
            lat,
            is_demo
        FROM live_alerts
        WHERE city_id = :city_id
          AND is_resolved = false
          AND lon IS NOT NULL
          AND lat IS NOT NULL
    """)
    active_alerts = db.execute(alert_sql, {"city_id": city_id}).fetchall()

    arepo = AssessmentRepository(db)
    communities: list[dict[str, Any]] = []

    for row in zone_rows:
        zone_uuid = UUID(row.zone_id)
        latest = arepo.latest_for_zone(zone_uuid)

        score = latest.overall_score if latest else None
        category = latest.category if latest else None
        confidence = latest.confidence if latest else None

        factors, reasons, explanation = _extract_components_and_factors(latest)
        severity = _impact_severity(score)

        # Check proximity to active alerts (within 3km)
        nearby_alerts = []
        for a in active_alerts:
            # Haversine distance approximation
            dlat = (a.lat - row.centroid_lat) * 111.0
            dlon = (a.lon - row.centroid_lon) * 111.0 * math.cos(math.radians(row.centroid_lat))
            dist_km = math.sqrt(dlat * dlat + dlon * dlon)
            if dist_km <= 3.5:
                nearby_alerts.append({
                    "id": a.id,
                    "title": a.title,
                    "alert_type": a.alert_type,
                    "severity": a.severity,
                    "distance_km": round(dist_km, 1),
                    "is_demo": bool(a.is_demo),
                })

        community = {
            "zone_id": row.zone_id,
            "zone_code": row.zone_code,
            "zone_name": row.zone_name,
            "centroid": {"lon": row.centroid_lon, "lat": row.centroid_lat},
            "boundary_geojson": json.loads(row.boundary_geojson) if row.boundary_geojson else None,
            "vulnerability_score": round(score, 1) if score is not None else None,
            "vulnerability_category": category or "Unscored",
            "impact_severity": severity,
            "impact_color": _impact_color(severity),
            "confidence": round(confidence, 2) if confidence is not None else None,
            "is_synthetic": bool(row.is_synthetic),
            "data_source_name": row.data_source_name,
            "top_vulnerability_factors": factors,
            "reasons": reasons,
            "explanation": explanation,
            "assessment_available": latest is not None,
            "hazard_only_score": (
                round(latest.hazard_only_score, 1)
                if latest and getattr(latest, "hazard_only_score", None) is not None
                else None
            ),
            "hazard_only_rank": getattr(latest, "hazard_only_rank", None) if latest else None,
            "multifactor_rank": getattr(latest, "multifactor_rank", None) if latest else None,
            "rank_uplift": getattr(latest, "rank_uplift", None) if latest else None,
            "nearby_active_alerts": nearby_alerts,
            "has_active_threat": len(nearby_alerts) > 0,
        }
        communities.append(community)

    # Sort communities: high vulnerability first, then by has_active_threat
    communities.sort(
        key=lambda c: (
            c["has_active_threat"],
            c["vulnerability_score"] or -1,
        ),
        reverse=True,
    )

    # Summary metrics
    severity_counts = {"critical": 0, "high": 0, "moderate": 0, "low": 0, "unknown": 0}
    for c in communities:
        s = c["impact_severity"]
        severity_counts[s] = severity_counts.get(s, 0) + 1

    scores = [c["vulnerability_score"] for c in communities if c["vulnerability_score"] is not None]
    synthetic_count = sum(1 for c in communities if c["is_synthetic"])

    return {
        "city_id": city_id,
        "city_name": city.name,
        "total_communities": len(communities),
        "severity_breakdown": severity_counts,
        "average_vulnerability_score": round(sum(scores) / len(scores), 1) if scores else None,
        "max_vulnerability_score": max(scores) if scores else None,
        "active_alerts_count": len(active_alerts),
        "synthetic_data_count": synthetic_count,
        "communities": communities,
        "generated_at": _utcnow().isoformat(),
        "disclaimer": (
            "Scores represent relative vulnerability in CRIVAL's model, not official flood predictions. "
            "Demo and synthetic datasets are clearly identified."
        ),
    }

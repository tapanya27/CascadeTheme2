"""Operational case briefing for a single community / zone."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.alert import LiveAlert
from app.models.assessment import VulnerabilityAssessment
from app.models.community_report import CommunityReport
from app.models.zone import Zone
from app.services.dashboard_service import DashboardService
from app.services.response_tasks import list_tasks, serialize_task, suggest_tasks


CATEGORY_OPS = {
    "low": "Low",
    "moderate": "Moderate",
    "high": "High",
    "critical": "Critical",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_case_briefing(
    db: Session, *, city_id: str, zone_id: uuid.UUID
) -> Optional[dict[str, Any]]:
    zone = (
        db.query(Zone)
        .options(joinedload(Zone.data_source))
        .filter(Zone.id == zone_id, Zone.city_id == city_id)
        .one_or_none()
    )
    if zone is None:
        return None

    assessment = (
        db.query(VulnerabilityAssessment)
        .filter(VulnerabilityAssessment.zone_id == zone_id)
        .order_by(VulnerabilityAssessment.created_at.desc())
        .first()
    )
    context = DashboardService(db).zone_context(zone_id, city_id=city_id)

    inputs = (assessment.inputs if assessment else {}) or {}
    pop = inputs.get("population")
    pop_synth = bool(inputs.get("population_is_synthetic"))
    pop_value: Any = None
    pop_label = "Not available"
    if pop is not None:
        try:
            pop_value = int(float(pop))
            pop_label = "Demo estimate" if pop_synth or (zone.data_source and zone.data_source.is_synthetic) else "Estimate from study data"
        except (TypeError, ValueError):
            pop_value = None
            pop_label = "Unknown"

    hc_km = inputs.get("nearest_healthcare_km")
    hc_name = inputs.get("nearest_healthcare_name")
    try:
        hc_km_f = float(hc_km) if hc_km is not None else None
    except (TypeError, ValueError):
        hc_km_f = None

    infra = context.infrastructure if context else []
    hazards = context.hazards if context else []
    hospitals = [i for i in infra if i.kind in {"hospital", "clinic", "emergency", "shelter"}]
    roads = [i for i in infra if i.kind in {"road", "bridge", "highway"}]

    alerts = (
        db.query(LiveAlert)
        .filter(LiveAlert.city_id == city_id)
        .order_by(LiveAlert.ingested_at.desc())
        .limit(80)
        .all()
    )
    # Zone-linked first, then city-wide demos/unresolved with coords so purple
    # markers appear on Action Center maps the same way community reports do.
    related_alerts: list[LiveAlert] = []
    seen_alert_ids: set[uuid.UUID] = set()
    for a in alerts:
        if a.zone_id == zone_id or (a.zone_id is None and not a.is_resolved):
            related_alerts.append(a)
            seen_alert_ids.add(a.id)
    for a in alerts:
        if a.id in seen_alert_ids:
            continue
        if (
            not a.is_resolved
            and a.has_reliable_coords
            and a.lat is not None
            and a.lon is not None
            and (a.is_demo or a.zone_id is not None)
        ):
            related_alerts.append(a)
            seen_alert_ids.add(a.id)
    related_alerts = related_alerts[:25]

    reports = (
        db.query(CommunityReport)
        .filter(CommunityReport.city_id == city_id)
        .order_by(CommunityReport.created_at.desc())
        .limit(40)
        .all()
    )
    # Prefer reports with coordinates near zone when available; else city open reports
    open_reports = [
        r
        for r in reports
        if r.verification_status in {"unverified", "verified"}
        and not (r.verification_status == "verified" and r.reviewed)
    ][:10]

    data_gaps: list[str] = []
    if assessment is None:
        data_gaps.append("No vulnerability assessment stored for this community yet.")
    elif assessment.confidence is not None and assessment.confidence < 0.5:
        data_gaps.append(
            "Assessment input coverage is low — treat rankings as provisional."
        )
    if not infra:
        data_gaps.append(
            "No intersecting infrastructure records found. Missing data does not "
            "prove that facilities are absent."
        )
    if not roads:
        data_gaps.append("No road/bridge features intersect this zone in the current dataset.")
    if pop_value is None:
        data_gaps.append("Population estimate not available for this zone.")

    category = assessment.category if assessment else None
    ops_status = CATEGORY_OPS.get(category or "", "Unknown")

    plain_why = None
    if assessment and assessment.explanation:
        plain_why = assessment.explanation
    elif assessment and assessment.reasons:
        plain_why = "; ".join(assessment.reasons[:2])
    else:
        plain_why = "Not enough scored information yet to explain priority."

    tasks = [serialize_task(t) for t in list_tasks(db, city_id, zone_id)]
    suggestions = suggest_tasks(db, city_id, zone_id)

    def _alert_dict(a: LiveAlert) -> dict[str, Any]:
        return {
            "id": str(a.id),
            "title": a.title,
            "description": a.description,
            "severity": a.severity,
            "alert_type": a.alert_type,
            "authenticity": a.authenticity,
            "is_demo": a.is_demo,
            "is_read": a.is_read,
            "is_acknowledged": a.is_acknowledged,
            "is_resolved": a.is_resolved,
            "has_reliable_coords": a.has_reliable_coords,
            "lat": a.lat,
            "lon": a.lon,
            "source_name": a.source_name,
            "observed_at": a.observed_at.isoformat() if a.observed_at else None,
            "ingested_at": a.ingested_at.isoformat() if a.ingested_at else None,
            "kind_label": (
                "Demo example"
                if a.is_demo
                else (
                    "Official alert"
                    if a.authenticity == "official"
                    else (
                        "Forecast / model outlook"
                        if a.authenticity == "forecast_model"
                        else "Alert notice"
                    )
                )
            ),
        }

    def _report_dict(r: CommunityReport) -> dict[str, Any]:
        loc = r.location or {}
        return {
            "id": str(r.id),
            "category": r.category,
            "text_redacted": r.text_redacted,
            "verification_status": r.verification_status,
            "needs_human_review": r.needs_human_review,
            "observation_kind": r.observation_kind,
            "location_precision": r.location_precision,
            "lat": loc.get("lat"),
            "lon": loc.get("lon"),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "kind_label": "Unverified community report",
        }

    return {
        "zone_id": str(zone.id),
        "city_id": zone.city_id,
        "zone_code": zone.code,
        "zone_name": zone.name,
        "description": zone.description,
        "operational_status": ops_status,
        "category": category,
        "overall_score": assessment.overall_score if assessment else None,
        "score_kind": "predicted_planning_score",
        "is_synthetic": bool(zone.data_source.is_synthetic) if zone.data_source else None,
        "data_source_name": zone.data_source.name if zone.data_source else None,
        "last_assessment_at": (
            assessment.created_at.isoformat() if assessment and assessment.created_at else None
        ),
        "confidence": assessment.confidence if assessment else None,
        "plain_language_why": plain_why,
        "situation_types": {
            "predicted_risk": assessment is not None,
            "observed_incident": len(hazards) > 0 or any(
                not a.is_demo and not a.is_resolved for a in related_alerts
            ),
            "confirmed_official_alert": any(
                a.authenticity == "official" and not a.is_resolved for a in related_alerts
            ),
            "demo_or_synthetic": bool(
                (zone.data_source and zone.data_source.is_synthetic)
                or any(a.is_demo for a in related_alerts)
            ),
        },
        "impact": {
            "population": {
                "value": pop_value,
                "label": pop_label,
                "is_demo_estimate": bool(pop_synth)
                or bool(zone.data_source and zone.data_source.is_synthetic),
            },
            "nearest_healthcare_km": hc_km_f,
            "nearest_healthcare_name": hc_name,
            "nearest_healthcare_note": (
                "Straight-line distance from assessment inputs — not travel time."
                if hc_km_f is not None
                else "Not available"
            ),
            "hospitals_clinics_in_zone": [
                {
                    "id": str(i.id),
                    "name": i.name,
                    "kind": i.kind,
                    "is_synthetic": i.is_synthetic,
                    "data_source_name": i.data_source_name,
                    "geometry": i.geometry,
                }
                for i in hospitals
            ],
            "roads_in_zone": [
                {
                    "id": str(i.id),
                    "name": i.name,
                    "kind": i.kind,
                    "is_synthetic": i.is_synthetic,
                    "geometry": i.geometry,
                }
                for i in roads
            ],
            "roads_blocked_reported": "Not available",
            "roads_blocked_note": (
                "No verified road-closure layer is wired. Do not treat missing "
                "records as proof that roads are clear or blocked."
            ),
            "hazard_observations": [
                {
                    "id": str(h.id),
                    "name": h.name,
                    "kind": h.kind,
                    "is_synthetic": h.is_synthetic,
                    "data_source_name": h.data_source_name,
                    "extra": h.extra,
                    "geometry": h.geometry,
                }
                for h in hazards
            ],
            "all_infrastructure": [
                {
                    "id": str(i.id),
                    "name": i.name,
                    "kind": i.kind,
                    "is_synthetic": i.is_synthetic,
                    "geometry": i.geometry,
                }
                for i in infra
            ],
        },
        "incidents": {
            "alerts": [_alert_dict(a) for a in related_alerts],
            "community_reports": [_report_dict(r) for r in open_reports],
            "unresolved_alert_count": sum(
                1 for a in related_alerts if not a.is_resolved
            ),
            "unverified_report_count": sum(
                1
                for r in open_reports
                if r.verification_status == "unverified" or r.needs_human_review
            ),
        },
        "data_gaps": data_gaps,
        "tasks": tasks,
        "suggested_tasks": suggestions,
        "geojson": None,  # filled by API from zone repository serialization if needed
        "generated_at": _utcnow().isoformat(),
        "disclaimer": (
            "Planning scores are not flood probabilities. Demo/synthetic rows are "
            "labelled. Missing infrastructure is a data gap, not proof of absence."
        ),
    }


def build_case_export(
    db: Session, *, city_id: str, zone_id: uuid.UUID
) -> Optional[dict[str, Any]]:
    briefing = build_case_briefing(db, city_id=city_id, zone_id=zone_id)
    if briefing is None:
        return None
    return {
        "export_kind": "case_report",
        "exported_at": _utcnow().isoformat(),
        "case": briefing,
        "notes": [
            "Export reflects stored database state at export time.",
            "Simulations must be re-run to refresh cascade results — not embedded unless provided by client.",
        ],
    }

"""CRUD + suggested tasks for the Disaster Response Action Center."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.alert import LiveAlert
from app.models.assessment import VulnerabilityAssessment
from app.models.community_report import CommunityReport
from app.models.response_task import ResponseTask
from app.models.zone import Zone

STATUSES = {"open", "assigned", "in_progress", "blocked", "done", "cancelled"}
PRIORITIES = {"urgent", "high", "medium", "low"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def serialize_task(row: ResponseTask) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "city_id": row.city_id,
        "zone_id": str(row.zone_id),
        "title": row.title,
        "description": row.description,
        "why_recommended": row.why_recommended,
        "priority": row.priority,
        "status": row.status,
        "source": row.source,
        "source_ref": row.source_ref,
        "assigned_to": row.assigned_to,
        "next_step": row.next_step,
        "notes": row.notes or [],
        "audit": row.audit or [],
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "disclaimer": (
            "Tasks are planning aids for officers — not automatic dispatch or "
            "approved government decisions."
        ),
    }


def _append_audit(row: ResponseTask, action: str, detail: str = "") -> None:
    trail = list(row.audit or [])
    trail.append(
        {
            "at": _utcnow().isoformat(),
            "action": action,
            "detail": detail,
        }
    )
    row.audit = trail


def list_tasks(
    db: Session,
    city_id: str,
    zone_id: uuid.UUID,
    *,
    include_done: bool = True,
) -> list[ResponseTask]:
    q = db.query(ResponseTask).filter(
        ResponseTask.city_id == city_id,
        ResponseTask.zone_id == zone_id,
    )
    if not include_done:
        q = q.filter(ResponseTask.status.notin_(["done", "cancelled"]))
    return q.order_by(ResponseTask.created_at.desc()).all()


def list_city_tasks(
    db: Session,
    city_id: str,
    *,
    include_done: bool = True,
    limit: int = 100,
) -> list[tuple[ResponseTask, str, str]]:
    """City-wide verification / response tasks with zone labels for the tasks inbox."""
    q = (
        db.query(ResponseTask, Zone.name, Zone.code)
        .join(Zone, Zone.id == ResponseTask.zone_id)
        .filter(ResponseTask.city_id == city_id)
    )
    if not include_done:
        q = q.filter(ResponseTask.status.notin_(["done", "cancelled"]))
    rows = q.order_by(ResponseTask.created_at.desc()).limit(max(1, min(limit, 500))).all()
    return [(task, zone_name, zone_code) for task, zone_name, zone_code in rows]


def serialize_task_with_zone(
    row: ResponseTask, zone_name: str, zone_code: str
) -> dict[str, Any]:
    data = serialize_task(row)
    data["zone_name"] = zone_name
    data["zone_code"] = zone_code
    return data


def create_task(
    db: Session,
    *,
    city_id: str,
    zone_id: uuid.UUID,
    title: str,
    description: str = "",
    why_recommended: str = "",
    priority: str = "medium",
    source: str = "officer",
    source_ref: Optional[str] = None,
    assigned_to: Optional[str] = None,
    next_step: Optional[str] = None,
) -> ResponseTask:
    zone = (
        db.query(Zone)
        .filter(Zone.id == zone_id, Zone.city_id == city_id)
        .one_or_none()
    )
    if zone is None:
        raise ValueError("Zone not found for this city.")

    row = ResponseTask(
        city_id=city_id,
        zone_id=zone_id,
        title=title[:512],
        description=description or "",
        why_recommended=why_recommended or "",
        priority=priority if priority in PRIORITIES else "medium",
        status="assigned" if assigned_to else "open",
        source=source,
        source_ref=source_ref,
        assigned_to=assigned_to,
        next_step=next_step,
        notes=[],
        audit=[],
    )
    _append_audit(row, "created", f"priority={row.priority}")
    if assigned_to:
        _append_audit(row, "assigned", assigned_to)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_task(
    db: Session,
    task_id: uuid.UUID,
    city_id: str,
    *,
    status: Optional[str] = None,
    assigned_to: Optional[str] = None,
    priority: Optional[str] = None,
    next_step: Optional[str] = None,
    note: Optional[str] = None,
) -> Optional[ResponseTask]:
    row = (
        db.query(ResponseTask)
        .filter(ResponseTask.id == task_id, ResponseTask.city_id == city_id)
        .one_or_none()
    )
    if row is None:
        return None

    if status is not None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {sorted(STATUSES)}")
        row.status = status
        _append_audit(row, "status_change", status)
        if status == "done":
            row.completed_at = _utcnow()
            _append_audit(row, "completed", "")
        elif status != "done":
            row.completed_at = None

    if assigned_to is not None:
        row.assigned_to = assigned_to or None
        if assigned_to:
            if row.status == "open":
                row.status = "assigned"
            _append_audit(row, "assigned", assigned_to)
        else:
            _append_audit(row, "unassigned", "")

    if priority is not None and priority in PRIORITIES:
        row.priority = priority
        _append_audit(row, "priority_change", priority)

    if next_step is not None:
        row.next_step = next_step
        _append_audit(row, "next_step", next_step[:200])

    if note is not None and note.strip():
        notes = list(row.notes or [])
        notes.append({"at": _utcnow().isoformat(), "text": note.strip()})
        row.notes = notes
        _append_audit(row, "note_added", note.strip()[:120])

    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return row


def suggest_tasks(
    db: Session,
    city_id: str,
    zone_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Derive recommended tasks from assessment, alerts, reports, and infra gaps."""
    zone = (
        db.query(Zone)
        .filter(Zone.id == zone_id, Zone.city_id == city_id)
        .one_or_none()
    )
    if zone is None:
        return []

    assessment = (
        db.query(VulnerabilityAssessment)
        .filter(VulnerabilityAssessment.zone_id == zone_id)
        .order_by(VulnerabilityAssessment.created_at.desc())
        .first()
    )
    alerts = (
        db.query(LiveAlert)
        .filter(
            LiveAlert.city_id == city_id,
            LiveAlert.is_resolved.is_(False),
        )
        .order_by(LiveAlert.ingested_at.desc())
        .limit(30)
        .all()
    )
    zone_alerts = [
        a for a in alerts if a.zone_id == zone_id or a.zone_id is None
    ]
    reports = (
        db.query(CommunityReport)
        .filter(
            CommunityReport.city_id == city_id,
            CommunityReport.verification_status != "rejected",
        )
        .order_by(CommunityReport.created_at.desc())
        .limit(40)
        .all()
    )

    suggestions: list[dict[str, Any]] = []

    if assessment and assessment.category in {"high", "critical"}:
        suggestions.append(
            {
                "title": "Assess this community on the ground",
                "description": (
                    f"{zone.name} is marked {assessment.category} by the planning score. "
                    "Confirm local conditions before committing resources."
                ),
                "why_recommended": (
                    assessment.explanation
                    or "High planning priority from the vulnerability assessment."
                ),
                "priority": "urgent" if assessment.category == "critical" else "high",
                "source": "risk_assessment",
                "source_ref": str(assessment.id),
                "next_step": "Assign a field team and record findings in task notes.",
            }
        )

    inputs = (assessment.inputs if assessment else {}) or {}
    hc_km = inputs.get("nearest_healthcare_km")
    if hc_km is not None:
        try:
            if float(hc_km) >= 3.0:
                suggestions.append(
                    {
                        "title": "Check hospital / clinic accessibility",
                        "description": (
                            f"Nearest mapped care is about {float(hc_km):.1f} km "
                            "(straight-line estimate). Verify road access."
                        ),
                        "why_recommended": "Travel burden appears elevated in assessment inputs.",
                        "priority": "high",
                        "source": "risk_assessment",
                        "source_ref": "nearest_healthcare_km",
                        "next_step": "Call the facility or send a scout vehicle.",
                    }
                )
        except (TypeError, ValueError):
            pass

    for a in zone_alerts[:3]:
        label = "Demo Alert" if a.is_demo else a.title
        suggestions.append(
            {
                "title": f"Review alert: {label}",
                "description": a.description[:280],
                "why_recommended": (
                    "Linked alert is still open for this city/area."
                    if not a.is_demo
                    else "Demo alert — practice the review workflow only."
                ),
                "priority": "high" if a.severity in {"warning", "urgent"} else "medium",
                "source": "alert",
                "source_ref": str(a.id),
                "next_step": "Acknowledge the alert, then verify on the map.",
            }
        )

    open_reports = [
        r
        for r in reports
        if r.verification_status == "unverified" or r.needs_human_review
    ][:3]
    for r in open_reports:
        suggestions.append(
            {
                "title": "Verify a community report",
                "description": (r.text_redacted or "")[:240],
                "why_recommended": "Unverified or review-needed community report.",
                "priority": "medium",
                "source": "community_report",
                "source_ref": str(r.id),
                "next_step": "Mark verification result after field or desk check.",
            }
        )

    if assessment is None:
        suggestions.append(
            {
                "title": "Update risk scores for this community",
                "description": "No assessment is stored yet for this zone.",
                "why_recommended": "Operational summary needs a current score.",
                "priority": "medium",
                "source": "system",
                "source_ref": None,
                "next_step": "Run assessments from Places That Need Attention.",
            }
        )

    return suggestions

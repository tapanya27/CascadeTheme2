"""Disaster Response Action Center APIs — case briefing, tasks, export."""

from __future__ import annotations

import csv
import io
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.cities.deps import parse_city_id
from app.database import get_db
from app.repositories.zones import ZoneRepository
from app.services import case_briefing, response_tasks as task_service

router = APIRouter(tags=["case-center"])


class CreateTaskBody(BaseModel):
    title: str = Field(..., min_length=3, max_length=512)
    description: Optional[str] = ""
    why_recommended: Optional[str] = ""
    priority: str = "medium"
    source: str = "officer"
    source_ref: Optional[str] = None
    assigned_to: Optional[str] = None
    next_step: Optional[str] = None


class UpdateTaskBody(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    priority: Optional[str] = None
    next_step: Optional[str] = None
    note: Optional[str] = None


@router.get("/api/zones/{zone_id}/case")
def get_case_briefing(
    zone_id: uuid.UUID,
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    data = case_briefing.build_case_briefing(db, city_id=city_id, zone_id=zone_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Community not found for this city.")
    zone = ZoneRepository(db).get(zone_id, city_id=city_id)
    if zone is not None:
        data["geojson"] = zone.geojson
    return data


@router.get("/api/tasks")
def list_city_tasks(
    city_id: str = Depends(parse_city_id),
    include_done: bool = Query(True),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = task_service.list_city_tasks(
        db, city_id, include_done=include_done, limit=limit
    )
    return {
        "city_id": city_id,
        "items": [
            task_service.serialize_task_with_zone(task, zone_name, zone_code)
            for task, zone_name, zone_code in rows
        ],
        "disclaimer": (
            "Verification and response tasks are planning aids — "
            "not automatic emergency dispatch."
        ),
    }


@router.get("/api/zones/{zone_id}/tasks")
def list_zone_tasks(
    zone_id: uuid.UUID,
    city_id: str = Depends(parse_city_id),
    include_done: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = task_service.list_tasks(
        db, city_id, zone_id, include_done=include_done
    )
    return {
        "zone_id": str(zone_id),
        "city_id": city_id,
        "items": [task_service.serialize_task(r) for r in rows],
        "suggested": task_service.suggest_tasks(db, city_id, zone_id),
        "disclaimer": (
            "Tasks are planning aids — not automatic emergency dispatch."
        ),
    }


@router.post("/api/zones/{zone_id}/tasks")
def create_zone_task(
    zone_id: uuid.UUID,
    body: CreateTaskBody,
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = task_service.create_task(
            db,
            city_id=city_id,
            zone_id=zone_id,
            title=body.title,
            description=body.description or "",
            why_recommended=body.why_recommended or "",
            priority=body.priority,
            source=body.source,
            source_ref=body.source_ref,
            assigned_to=body.assigned_to,
            next_step=body.next_step,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return task_service.serialize_task(row)


@router.post("/api/tasks/{task_id}/update")
def update_task(
    task_id: uuid.UUID,
    body: UpdateTaskBody,
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = task_service.update_task(
            db,
            task_id,
            city_id,
            status=body.status,
            assigned_to=body.assigned_to,
            priority=body.priority,
            next_step=body.next_step,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found for this city.")
    return task_service.serialize_task(row)


@router.get("/api/zones/{zone_id}/case/export")
def export_case(
    zone_id: uuid.UUID,
    city_id: str = Depends(parse_city_id),
    format: str = Query("json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
):
    payload = case_briefing.build_case_export(db, city_id=city_id, zone_id=zone_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Community not found for this city.")

    if format == "json":
        return payload

    case = payload["case"]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["field", "value"])
    writer.writerow(["zone_id", case["zone_id"]])
    writer.writerow(["zone_name", case["zone_name"]])
    writer.writerow(["city_id", case["city_id"]])
    writer.writerow(["operational_status", case["operational_status"]])
    writer.writerow(["category", case.get("category") or ""])
    writer.writerow(["is_synthetic", case.get("is_synthetic")])
    writer.writerow(["last_assessment_at", case.get("last_assessment_at") or ""])
    writer.writerow(["plain_language_why", case.get("plain_language_why") or ""])
    pop = case["impact"]["population"]
    writer.writerow(
        [
            "population",
            pop["value"] if pop["value"] is not None else "Not available",
        ]
    )
    writer.writerow(["population_label", pop["label"]])
    writer.writerow(
        ["unresolved_alerts", case["incidents"]["unresolved_alert_count"]]
    )
    writer.writerow(
        ["unverified_reports", case["incidents"]["unverified_report_count"]]
    )
    for gap in case.get("data_gaps") or []:
        writer.writerow(["data_gap", gap])
    for t in case.get("tasks") or []:
        writer.writerow(
            [
                "task",
                f"{t.get('status')}|{t.get('priority')}|{t.get('title')}|assigned={t.get('assigned_to')}",
            ]
        )
    for a in case["incidents"].get("alerts") or []:
        writer.writerow(
            [
                "alert",
                f"{a.get('kind_label')}|{a.get('title')}|resolved={a.get('is_resolved')}",
            ]
        )

    buf.seek(0)
    filename = f"case_{case['zone_code']}_{city_id}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

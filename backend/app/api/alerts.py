"""Live alert notification APIs — list, status actions, demo + Open-Meteo poll."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.cities.deps import parse_city_id
from app.database import get_db
from app.models.alert import LiveAlert
from app.services import alerts as alert_service

router = APIRouter(tags=["alerts"])


class DemoAlertBody(BaseModel):
    alert_type: str = Field(
        default="weather_rainfall",
        description="weather_rainfall | flood_warning | road_closure | infrastructure | community_report | risk_change",
    )
    severity: str = Field(default="warning")


class AlertActionBody(BaseModel):
    action: str = Field(..., description="read | acknowledge | resolve")


@router.get("/api/alerts")
def list_alerts(
    city_id: str = Depends(parse_city_id),
    include_resolved: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = alert_service.list_alerts(
        db, city_id, include_resolved=include_resolved, limit=limit
    )
    return {
        "city_id": city_id,
        "unread_count": alert_service.unread_count(db, city_id),
        "items": [alert_service.serialize_alert(r) for r in rows],
        "disclaimer": (
            "Demo alerts are examples only. Open-Meteo items are forecast-model "
            "outlooks, not official government warnings."
        ),
    }


@router.get("/api/alerts/unread-count")
def get_unread_count(
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return {
        "city_id": city_id,
        "unread_count": alert_service.unread_count(db, city_id),
    }


@router.get("/api/alerts/sources")
def get_sources(
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return alert_service.source_status(db, city_id)


@router.get("/api/alerts/{alert_id}")
def get_alert(
    alert_id: uuid.UUID,
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = (
        db.query(LiveAlert)
        .filter(LiveAlert.id == alert_id, LiveAlert.city_id == city_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found for this city.")
    return alert_service.serialize_alert(row)


@router.post("/api/alerts/{alert_id}/action")
def alert_action(
    alert_id: uuid.UUID,
    body: AlertActionBody,
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    action = body.action.strip().lower()
    if action == "read":
        row = alert_service.mark_read(db, alert_id, city_id)
    elif action == "acknowledge":
        row = alert_service.acknowledge(db, alert_id, city_id)
    elif action == "resolve":
        row = alert_service.resolve(db, alert_id, city_id)
    else:
        raise HTTPException(
            status_code=400,
            detail="action must be one of: read, acknowledge, resolve",
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found for this city.")
    return alert_service.serialize_alert(row)


@router.post("/api/alerts/mark-all-read")
def mark_all_read(
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    n = alert_service.mark_all_read(db, city_id)
    return {
        "city_id": city_id,
        "marked": n,
        "unread_count": alert_service.unread_count(db, city_id),
    }


@router.post("/api/alerts/demo")
def create_demo(
    body: DemoAlertBody,
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a clearly labeled Demo Alert for the map notification workflow."""
    row = alert_service.create_demo_alert(
        db,
        city_id,
        alert_type=body.alert_type,
        severity=body.severity,
    )
    return {
        "created": True,
        "alert": alert_service.serialize_alert(row),
        "disclaimer": "This is a Demo Alert (example only) — not a real incident.",
    }


@router.post("/api/alerts/poll")
def poll_feeds(
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Poll configured real feeds (Open-Meteo forecast) and return ingest result."""
    om = alert_service.poll_open_meteo_forecast(db, city_id)
    return {
        "city_id": city_id,
        "unread_count": alert_service.unread_count(db, city_id),
        "results": [om],
    }

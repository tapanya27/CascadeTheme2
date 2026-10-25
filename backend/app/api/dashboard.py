"""Dashboard overview and map layer endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.cities.deps import parse_city_id
from app.database import get_db
from app.schemas.dashboard import (
    MapLayersResponse,
    OverviewResponse,
    ZoneContextResponse,
)
from app.services.dashboard_service import DashboardService

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard/overview", response_model=OverviewResponse)
def dashboard_overview(
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> OverviewResponse:
    return DashboardService(db).overview(city_id=city_id)


@router.get("/api/map/layers", response_model=MapLayersResponse)
def map_layers(
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> MapLayersResponse:
    return DashboardService(db).map_layers(city_id=city_id)


@router.get("/api/zones/{zone_id}/context", response_model=ZoneContextResponse)
def zone_context(
    zone_id: str,
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> ZoneContextResponse:
    try:
        uid = UUID(zone_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid zone id") from exc
    ctx = DashboardService(db).zone_context(uid, city_id=city_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Zone not found for this city")
    return ctx

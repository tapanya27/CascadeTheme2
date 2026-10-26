"""Community Risk & Impact API endpoints."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.cities.deps import parse_city_id
from app.database import get_db
from app.services import community_impact as impact_service

router = APIRouter(tags=["community-impact"])


class CustomImpactAnalysisRequest(BaseModel):
    alert_id: Optional[UUID] = Field(None, description="Optional alert ID to analyze")
    lon: Optional[float] = Field(None, description="Longitude for spatial analysis")
    lat: Optional[float] = Field(None, description="Latitude for spatial analysis")
    radius_m: Optional[float] = Field(None, ge=500, le=20000, description="Custom impact radius in meters")
    alert_type: Optional[str] = Field(
        None,
        description="weather_rainfall | flood_warning | road_closure | infrastructure | community_report | risk_change",
    )


@router.get("/api/community-impact/overview")
def get_community_risk_overview(
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Get city-wide community risk & impact overview.
    Returns vulnerability scores, severities, top reasons, and active alert proximity
    for every community in the selected city.
    """
    return impact_service.get_city_community_risk_overview(db, city_id)


@router.get("/api/community-impact/alert/{alert_id}")
def get_alert_community_impact(
    alert_id: UUID,
    radius_m: Optional[float] = Query(None, ge=500, le=20000),
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Analyze nearby communities, infrastructure, and dependency pathways
    for a specific alert in the selected city.
    """
    result = impact_service.analyze_alert_impact(
        db,
        alert_id=alert_id,
        city_id=city_id,
        radius_m=radius_m,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/api/community-impact/analyze")
def analyze_custom_community_impact(
    body: CustomImpactAnalysisRequest,
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Analyze community risk and impact for arbitrary coordinates or an alert
    with optional custom radius and alert context.
    """
    result = impact_service.analyze_alert_impact(
        db,
        alert_id=body.alert_id,
        city_id=city_id,
        lon=body.lon,
        lat=body.lat,
        radius_m=body.radius_m,
        alert_type=body.alert_type,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

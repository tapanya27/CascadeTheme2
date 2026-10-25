"""Zone endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.cities.deps import parse_city_id
from app.database import get_db
from app.repositories.assessments import AssessmentRepository
from app.repositories.zones import ZoneRepository
from app.schemas.assessment import ZoneExplanationOut
from app.schemas.zone import ZoneListResponse, ZoneOut

router = APIRouter(tags=["zones"])


@router.get("/api/zones", response_model=ZoneListResponse)
def list_zones(
    city_id: str = Depends(parse_city_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ZoneListResponse:
    repo = ZoneRepository(db)
    items, total = repo.list_zones(page=page, page_size=page_size, city_id=city_id)
    arepo = AssessmentRepository(db)
    enriched: list[ZoneOut] = []
    for z in items:
        latest = arepo.latest_for_zone(z.id)
        data = z.model_dump()
        if latest:
            data["latest_score"] = latest.overall_score
            data["latest_category"] = latest.category
            data["latest_confidence"] = latest.confidence
            data["latest_assessment_id"] = str(latest.id)
            data["hazard_only_score"] = getattr(latest, "hazard_only_score", None)
            data["hazard_only_rank"] = getattr(latest, "hazard_only_rank", None)
            data["multifactor_rank"] = getattr(latest, "multifactor_rank", None)
            data["rank_uplift"] = getattr(latest, "rank_uplift", None)
        enriched.append(ZoneOut.model_validate(data))
    return ZoneListResponse(
        items=enriched,
        total=total,
        page=page,
        page_size=page_size,
        pages=repo.pages(total, page_size),
    )


@router.get("/api/zones/{zone_id}", response_model=ZoneOut)
def get_zone(
    zone_id: str,
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> ZoneOut:
    try:
        uid = UUID(zone_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid zone id") from exc
    repo = ZoneRepository(db)
    zone = repo.get(uid, city_id=city_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found for this city")
    arepo = AssessmentRepository(db)
    latest = arepo.latest_for_zone(uid)
    data = zone.model_dump()
    if latest:
        data["latest_score"] = latest.overall_score
        data["latest_category"] = latest.category
        data["latest_confidence"] = latest.confidence
        data["latest_assessment_id"] = str(latest.id)
        data["hazard_only_score"] = getattr(latest, "hazard_only_score", None)
        data["hazard_only_rank"] = getattr(latest, "hazard_only_rank", None)
        data["multifactor_rank"] = getattr(latest, "multifactor_rank", None)
        data["rank_uplift"] = getattr(latest, "rank_uplift", None)
    return ZoneOut.model_validate(data)


@router.get("/api/zones/{zone_id}/explanation", response_model=ZoneExplanationOut)
def zone_explanation(
    zone_id: str,
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> ZoneExplanationOut:
    try:
        uid = UUID(zone_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid zone id") from exc
    zrepo = ZoneRepository(db)
    zone = zrepo.get(uid, city_id=city_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found for this city")
    arepo = AssessmentRepository(db)
    latest = arepo.latest_for_zone(uid)
    if not latest:
        return ZoneExplanationOut(
            zone_id=uid,
            zone_code=zone.code,
            zone_name=zone.name,
            assessment=None,
            message=(
                "No assessment found for this zone. "
                "POST /api/assessments/run with city_id to compute scores."
            ),
        )
    return ZoneExplanationOut(
        zone_id=uid,
        zone_code=zone.code,
        zone_name=zone.name,
        assessment=arepo.to_out(latest),
        message=None,
    )

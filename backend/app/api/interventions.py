"""Intervention scenario endpoints."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.cities.deps import parse_city_id
from app.database import get_db
from app.models.intervention import InterventionType
from app.schemas.intervention import (
    InterventionCompareRequest,
    InterventionListResponse,
    InterventionScenarioOut,
)
from app.security import check_rate_limit
from app.services.intervention_service import (
    InterventionEvaluationError,
    InterventionService,
    SIMULATION_DISCLAIMER,
)

router = APIRouter(tags=["interventions"])


def _to_out(row) -> InterventionScenarioOut:
    limitations = row.limitations
    if isinstance(limitations, dict) and "items" in limitations:
        limitations = limitations["items"]
    return InterventionScenarioOut(
        id=row.id,
        zone_id=row.zone_id,
        zone_code=row.zone.code if row.zone else None,
        zone_name=row.zone.name if row.zone else None,
        name=row.name,
        intervention_type=row.intervention_type.value
        if hasattr(row.intervention_type, "value")
        else str(row.intervention_type),
        scoring_version=row.scoring_version,
        assumptions=row.assumptions or {},
        inputs=row.inputs or {},
        baseline=row.baseline or {},
        results=row.results or {},
        limitations=limitations if isinstance(limitations, list) else list(limitations or []),
        provenance=row.provenance or {},
        notes=row.notes,
        created_at=row.created_at,
    )


@router.get("/api/interventions", response_model=InterventionListResponse)
def list_interventions(
    city_id: str = Depends(parse_city_id),
    zone_id: Optional[UUID] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> InterventionListResponse:
    svc = InterventionService(db)
    rows = svc.list_scenarios(zone_id=zone_id, limit=limit, city_id=city_id)
    return InterventionListResponse(
        items=[_to_out(r) for r in rows],
        total=len(rows),
        catalog=svc.list_catalog(),
    )


@router.get("/api/interventions/{scenario_id}", response_model=InterventionScenarioOut)
def get_intervention(
    scenario_id: str,
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> InterventionScenarioOut:
    try:
        uid = UUID(scenario_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid scenario id") from exc
    row = InterventionService(db).get(uid, city_id=city_id)
    if not row:
        raise HTTPException(
            status_code=404,
            detail="Scenario not found for this city",
        )
    return _to_out(row)


@router.post("/api/interventions/compare", response_model=InterventionScenarioOut)
def compare_intervention(
    body: InterventionCompareRequest,
    request: Request,
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> InterventionScenarioOut:
    check_rate_limit(request, expensive=True)
    try:
        itype = InterventionType(body.intervention_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unknown intervention_type. See GET /api/interventions catalog "
                "for supported types."
            ),
        ) from exc

    try:
        row = InterventionService(db).compare(
            zone_id=body.zone_id,
            intervention_type=itype,
            name=body.name,
            params=body.params or {},
            weight_overrides=body.weight_overrides,
            notes=body.notes,
            persist=body.persist,
            city_id=city_id,
        )
    except InterventionEvaluationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Scenario comparison failed. Check inputs and try again.",
        )

    if isinstance(row, dict):
        raise HTTPException(
            status_code=400,
            detail="persist=false is not supported for this endpoint; set persist=true.",
        )
    out = _to_out(row)
    lim = list(out.limitations) if isinstance(out.limitations, list) else []
    if SIMULATION_DISCLAIMER not in lim:
        lim.insert(0, SIMULATION_DISCLAIMER)
    out.limitations = lim
    return out

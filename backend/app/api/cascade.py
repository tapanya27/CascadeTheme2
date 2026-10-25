"""Cascading-failure simulation API."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.cities.deps import parse_city_id
from app.database import get_db
from app.security import check_rate_limit
from app.services.cascade_simulator import SCENARIO_TYPES, CascadeSimulator

router = APIRouter(tags=["cascade"])


class CascadeRequest(BaseModel):
    scenario_type: str = Field(
        ...,
        description=f"One of: {sorted(SCENARIO_TYPES)}",
    )
    failed_infra_ids: Optional[list[str]] = None
    lost_source_kinds: Optional[list[str]] = None
    zone_ids: Optional[list[UUID]] = None


@router.get("/api/cascade/scenarios")
def list_scenario_types():
    return {
        "scenario_types": sorted(SCENARIO_TYPES),
        "notes": [
            "Simulations recalculate accessibility proxies and dual rankings.",
            "Assumed/hypothesized edges are not causal proof.",
            "Results are scoped to the requested city_id.",
        ],
    }


@router.post("/api/cascade/simulate")
def simulate(
    body: CascadeRequest,
    request: Request,
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
):
    check_rate_limit(request, expensive=True)
    try:
        return CascadeSimulator(db).simulate(
            scenario_type=body.scenario_type,
            failed_infra_ids=body.failed_infra_ids,
            lost_source_kinds=body.lost_source_kinds,
            zone_ids=body.zone_ids,
            city_id=city_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

"""Resilience under data-loss simulation API."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.cities.deps import parse_city_id
from app.database import get_db
from app.security import check_rate_limit
from app.services.resilience_service import ResilienceService

router = APIRouter(tags=["resilience"])


class ResilienceRequest(BaseModel):
    drop_fractions: list[float] = Field(default_factory=lambda: [0.2, 0.4, 0.6])
    seed: int = 42
    zone_ids: Optional[list[UUID]] = None
    include_noise_tests: bool = True
    include_cascade_during_loss: bool = True


@router.post("/api/resilience/run")
def run_resilience(
    body: ResilienceRequest,
    request: Request,
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
):
    check_rate_limit(request, expensive=True)
    return ResilienceService(db).run(
        drop_fractions=body.drop_fractions,
        seed=body.seed,
        zone_ids=body.zone_ids,
        include_noise_tests=body.include_noise_tests,
        include_cascade_during_loss=body.include_cascade_during_loss,
        city_id=city_id,
    )

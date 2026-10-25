"""Dependency graph endpoint."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.cities.deps import parse_city_id
from app.database import get_db
from app.schemas.dependency import DependencyGraphOut
from app.services.dependency_graph import DependencyGraphService

router = APIRouter(tags=["dependencies"])


@router.get("/api/dependency-graph", response_model=DependencyGraphOut)
def get_dependency_graph(
    city_id: str = Depends(parse_city_id),
    zone_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
) -> DependencyGraphOut:
    try:
        return DependencyGraphService(db).serialize(
            zone_id=zone_id, city_id=city_id
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"Failed to build dependency graph: {exc}"
        ) from exc

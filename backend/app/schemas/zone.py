"""Zone API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ZoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    city_id: str
    code: str
    name: str
    description: Optional[str] = None
    properties: dict[str, Any] = Field(default_factory=dict)
    data_source_id: UUID
    data_source_name: Optional[str] = None
    is_synthetic: Optional[bool] = None
    geojson: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    # Optional Module 2 enrichment from latest assessment
    latest_score: Optional[float] = None
    latest_category: Optional[str] = None
    latest_confidence: Optional[float] = None
    latest_assessment_id: Optional[str] = None
    hazard_only_score: Optional[float] = None
    hazard_only_rank: Optional[int] = None
    multifactor_rank: Optional[int] = None
    rank_uplift: Optional[int] = None


class ZoneListResponse(BaseModel):
    items: list[ZoneOut]
    total: int
    page: int
    page_size: int
    pages: int

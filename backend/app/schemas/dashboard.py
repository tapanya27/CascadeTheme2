"""Dashboard and map response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CategoryCount(BaseModel):
    category: str
    count: int
    label: str


class HighPriorityZone(BaseModel):
    zone_id: UUID
    code: str
    name: str
    overall_score: Optional[float] = None
    category: Optional[str] = None
    is_synthetic: Optional[bool] = None
    confidence: Optional[float] = None
    hazard_only_score: Optional[float] = None
    hazard_only_rank: Optional[int] = None
    multifactor_rank: Optional[int] = None
    rank_uplift: Optional[int] = None


class HealthcareSummary(BaseModel):
    zones_with_travel_burden: int
    average_nearest_healthcare_km: Optional[float] = None
    note: str


class DataFreshness(BaseModel):
    latest_assessment_at: Optional[datetime] = None
    latest_run_id: Optional[UUID] = None
    scoring_version: Optional[str] = None
    data_source_count: int
    synthetic_source_count: int
    authentic_source_count: int


class OverviewResponse(BaseModel):
    city_id: str
    total_zones: int
    zones_assessed: int
    category_counts: list[CategoryCount]
    high_priority: list[HighPriorityZone]
    healthcare: HealthcareSummary
    freshness: DataFreshness
    key_findings: list[str]
    map_preview_zone_ids: list[UUID] = Field(default_factory=list)
    disclaimer: str


class MapFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[dict[str, Any]]
    meta: dict[str, Any] = Field(default_factory=dict)


class MapLayersResponse(BaseModel):
    city_id: str
    zones: MapFeatureCollection
    hazards: MapFeatureCollection
    infrastructure: MapFeatureCollection
    community_reports: MapFeatureCollection = Field(
        default_factory=lambda: MapFeatureCollection(features=[], meta={})
    )
    generated_at: datetime
    notes: list[str]


class ZoneContextItem(BaseModel):
    id: UUID
    name: str
    kind: str
    is_synthetic: bool
    data_source_name: Optional[str] = None
    properties: dict[str, Any] = Field(default_factory=dict)
    geometry: Optional[dict[str, Any]] = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ZoneContextResponse(BaseModel):
    zone_id: UUID
    city_id: str
    zone_code: str
    zone_name: str
    is_synthetic: Optional[bool] = None
    hazards: list[ZoneContextItem]
    infrastructure: list[ZoneContextItem]
    note: str

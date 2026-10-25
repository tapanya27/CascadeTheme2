"""Shared response schemas."""

from __future__ import annotations

from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    postgis: bool
    postgis_version: Optional[str] = None
    error: Optional[str] = None


class MetadataResponse(BaseModel):
    project: str
    module: str
    study_area: str
    spatial_srid: int
    database_required: str = "PostgreSQL with PostGIS"
    endpoints: List[str]
    notes: List[str] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    detail: str
    errors: Optional[List[dict[str, Any]]] = None


class PaginatedResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int

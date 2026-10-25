"""Data import / export / source schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DataSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    city_id: str
    name: str
    kind: str
    is_synthetic: bool
    description: Optional[str] = None
    provider: Optional[str] = None
    retrieval_url: Optional[str] = None
    license_note: Optional[str] = None
    retrieved_at: Optional[datetime] = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ValidationIssue(BaseModel):
    row: Optional[int] = None
    field: Optional[str] = None
    message: str
    severity: str = "error"  # error | warning


class ValidationResult(BaseModel):
    valid: bool
    record_type: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    issues: list[ValidationIssue] = Field(default_factory=list)
    preview: list[dict[str, Any]] = Field(default_factory=list)
    detected_crs: Optional[str] = None
    target_srid: int = 4326
    duplicate_count: int = 0


class ImportRequestMeta(BaseModel):
    source_name: Optional[str] = None
    record_type: str = Field(
        description="One of: zones, infrastructure, hazards"
    )
    commit: bool = True


class ImportResult(BaseModel):
    committed: bool
    validation: ValidationResult
    inserted: int = 0
    skipped_duplicates: int = 0
    data_source_id: Optional[UUID] = None
    message: str


class ExportResponse(BaseModel):
    format: str
    generated_at: datetime
    zones: list[dict[str, Any]] = Field(default_factory=list)
    infrastructure: list[dict[str, Any]] = Field(default_factory=list)
    hazards: list[dict[str, Any]] = Field(default_factory=list)
    data_sources: list[dict[str, Any]] = Field(default_factory=list)
    note: str = (
        "Records include data_source provenance. Synthetic rows are labelled "
        "is_synthetic=true and must not be treated as verified measurements."
    )

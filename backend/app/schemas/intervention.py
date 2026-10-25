"""Intervention scenario API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InterventionCompareRequest(BaseModel):
    zone_id: UUID
    intervention_type: str
    name: str = Field(min_length=1, max_length=255)
    params: dict[str, Any] = Field(default_factory=dict)
    weight_overrides: Optional[dict[str, float]] = None
    notes: Optional[str] = None
    persist: bool = True


class InterventionScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    zone_id: UUID
    zone_code: Optional[str] = None
    zone_name: Optional[str] = None
    name: str
    intervention_type: str
    scoring_version: str
    assumptions: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    baseline: dict[str, Any] = Field(default_factory=dict)
    results: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] | dict[str, Any] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None
    created_at: datetime
    simulation_label: str = (
        "SIMULATION — not a guaranteed real-world outcome"
    )


class InterventionListResponse(BaseModel):
    items: list[InterventionScenarioOut]
    total: int
    catalog: list[dict[str, Any]] = Field(default_factory=list)


class SensitivityRequest(BaseModel):
    zone_ids: Optional[list[UUID]] = None
    perturbation: float = Field(default=0.2, gt=0, lt=1)


class SensitivityResponse(BaseModel):
    method: str
    perturbation: float | None = None
    disclaimer: str
    assumptions: list[str] = Field(default_factory=list)
    baseline_ranking: list[dict[str, Any]] = Field(default_factory=list)
    baseline_top3: list[str] = Field(default_factory=list)
    variants: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)

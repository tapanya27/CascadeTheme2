"""Assessment and explanation API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ComponentScoreOut(BaseModel):
    key: str
    label: str
    status: str
    raw_value: Optional[float] = None
    normalized_score: Optional[float] = None
    weight_configured: float
    weight_effective: float
    direction: str
    is_synthetic: bool
    contribution: Optional[float] = None
    reason: str
    source_refs: list[str] = Field(default_factory=list)
    limitations: str = ""


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    zone_id: UUID
    zone_code: Optional[str] = None
    zone_name: Optional[str] = None
    scoring_version: str
    overall_score: Optional[float] = None
    category: Optional[str] = None
    confidence: float
    components: list[ComponentScoreOut] | list[dict[str, Any]] = Field(
        default_factory=list
    )
    weights_used: dict[str, Any] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    data_quality: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    explanation: str
    created_at: datetime
    # Dual ranking (hazard-only vs multi-factor)
    hazard_only_score: Optional[float] = None
    hazard_only_rank: Optional[int] = None
    multifactor_rank: Optional[int] = None
    rank_uplift: Optional[int] = None


class ZoneExplanationOut(BaseModel):
    zone_id: UUID
    zone_code: str
    zone_name: str
    assessment: Optional[AssessmentOut] = None
    message: Optional[str] = None


class RunAssessmentsRequest(BaseModel):
    zone_ids: Optional[list[UUID]] = None
    weight_overrides: Optional[dict[str, float]] = None
    seed_dependency_graph: bool = True


class RunAssessmentsResponse(BaseModel):
    run_id: UUID
    scoring_version: str
    assessed: int
    assessments: list[AssessmentOut]
    methodology: dict[str, Any]
    dependency_graph_seeded: bool = False
    dual_rankings: list[dict[str, Any]] = Field(default_factory=list)


class LatestAssessmentsResponse(BaseModel):
    scoring_version: Optional[str] = None
    run_id: Optional[UUID] = None
    items: list[AssessmentOut]
    total: int

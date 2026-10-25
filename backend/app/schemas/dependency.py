"""Dependency graph API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GraphNodeOut(BaseModel):
    id: str
    label: str
    kind: str = "factor"


class GraphEdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: str
    target: str
    relationship_type: str
    evidence: Optional[str] = None
    evidence_kind: str
    strength: Optional[float] = None
    confidence: Optional[float] = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    zone_id: Optional[UUID] = None


class DependencyGraphOut(BaseModel):
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]
    cycles: list[list[str]] = Field(default_factory=list)
    is_dag: bool
    notes: list[str] = Field(default_factory=list)
    generated_at: datetime

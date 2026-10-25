"""Persisted intervention scenario comparisons (Module 4)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InterventionType(str, enum.Enum):
    place_temporary_resource = "place_temporary_resource"
    accessibility_improvement = "accessibility_improvement"
    alternative_emergency_route = "alternative_emergency_route"
    compare_resource_placements = "compare_resource_placements"


class InterventionScenario(Base):
    __tablename__ = "intervention_scenarios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    zone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("zones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    intervention_type: Mapped[InterventionType] = mapped_column(
        Enum(InterventionType, name="intervention_type", native_enum=True),
        nullable=False,
        index=True,
    )
    scoring_version: Mapped[str] = mapped_column(String(64), nullable=False)
    assumptions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    inputs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    baseline: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    results: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    limitations: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    zone = relationship("Zone", back_populates="intervention_scenarios")

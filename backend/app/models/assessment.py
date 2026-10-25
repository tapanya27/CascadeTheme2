"""Persisted vulnerability assessment results."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class VulnerabilityAssessment(Base):
    __tablename__ = "vulnerability_assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    zone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("zones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scoring_version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    components: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    weights_used: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    reasons: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    data_quality: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    limitations: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    source_refs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    inputs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Dual ranking (Phase 4) — overall_score remains multi-factor
    hazard_only_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hazard_only_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    multifactor_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rank_uplift: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    zone = relationship("Zone", back_populates="assessments")

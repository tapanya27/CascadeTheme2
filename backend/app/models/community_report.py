"""Privacy-conscious community / corpus disaster reports."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CommunityReport(Base):
    __tablename__ = "community_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    city_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    text_redacted: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    near_duplicate_key: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    disaster_related: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    disaster_related_proba: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    labels: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    label_probas: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    # Primary display category (e.g. flooding, blocked_roads, medical_needs)
    category: Mapped[str] = mapped_column(
        String(64), nullable=False, default="unclassified", server_default="unclassified"
    )
    needs_human_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # unverified (default) | verified | rejected
    verification_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="unverified",
        server_default="unverified",
        index=True,
    )
    location_precision: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown"
    )
    location: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    observation_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unverified"
    )
    source_reliability: Mapped[str] = mapped_column(
        String(64), nullable=False, default="unverified_community"
    )
    observed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

"""Live / demo community alerts — distinct from community reports and model scores."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LiveAlert(Base):
    """Normalized alert from a configured source or the labeled demo adapter."""

    __tablename__ = "live_alerts"
    __table_args__ = (
        UniqueConstraint(
            "source_name", "source_event_id", name="uq_live_alerts_source_event"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    city_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_event_id: Mapped[str] = mapped_column(String(256), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    has_reliable_coords: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    zone_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    area_label: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="unverified",
        server_default="unverified",
    )
    # official | forecast_model | community | demo | risk_model
    authenticity: Mapped[str] = mapped_column(
        String(32), nullable=False, default="demo", server_default="demo"
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    observed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    # User workflow statuses (independent of each other)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

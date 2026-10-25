"""Hazard observation model (flood-related and related hazards)."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any, Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class HazardType(str, enum.Enum):
    flood = "flood"
    waterlogging = "waterlogging"
    other = "other"


class SeverityLevel(str, enum.Enum):
    low = "low"
    moderate = "moderate"
    high = "high"
    severe = "severe"
    unknown = "unknown"


class HazardObservation(Base):
    __tablename__ = "hazard_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    city_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    hazard_type: Mapped[HazardType] = mapped_column(
        Enum(HazardType, name="hazard_type", native_enum=True),
        nullable=False,
        index=True,
    )
    severity: Mapped[SeverityLevel] = mapped_column(
        Enum(SeverityLevel, name="severity_level", native_enum=True),
        nullable=False,
        default=SeverityLevel.unknown,
    )
    observed_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    geometry = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True),
        nullable=True,
    )
    properties: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("zones.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    zone = relationship("Zone", back_populates="hazards")
    data_source = relationship("DataSource", back_populates="hazards")

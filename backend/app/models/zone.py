"""Geographic zone model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Zone(Base):
    __tablename__ = "zones"
    __table_args__ = (
        UniqueConstraint("city_id", "code", name="uq_zones_city_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    city_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Polygon / MultiPolygon in WGS84
    boundary = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )
    properties: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
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

    data_source = relationship("DataSource", back_populates="zones")
    infrastructure = relationship("Infrastructure", back_populates="zone")
    hazards = relationship("HazardObservation", back_populates="zone")
    assessments = relationship(
        "VulnerabilityAssessment", back_populates="zone", cascade="all, delete-orphan"
    )
    intervention_scenarios = relationship(
        "InterventionScenario", back_populates="zone", cascade="all, delete-orphan"
    )

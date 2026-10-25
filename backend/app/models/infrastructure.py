"""Infrastructure (hospitals, roads, emergency facilities) model."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InfrastructureType(str, enum.Enum):
    hospital = "hospital"
    clinic = "clinic"
    emergency_facility = "emergency_facility"
    road = "road"
    other = "other"


class Infrastructure(Base):
    __tablename__ = "infrastructure"
    __table_args__ = (
        UniqueConstraint(
            "external_id", "data_source_id", name="uq_infra_external_source"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    city_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    infrastructure_type: Mapped[InfrastructureType] = mapped_column(
        Enum(InfrastructureType, name="infrastructure_type", native_enum=True),
        nullable=False,
        index=True,
    )
    # Point for facilities; LineString/MultiLineString for roads — use Geometry
    geometry = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True),
        nullable=False,
    )
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    properties: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
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
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    zone = relationship("Zone", back_populates="infrastructure")
    data_source = relationship("DataSource", back_populates="infrastructure")

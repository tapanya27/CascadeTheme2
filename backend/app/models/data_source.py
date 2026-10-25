"""Data source provenance model."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Enum, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DataSourceKind(str, enum.Enum):
    authentic = "authentic"
    synthetic = "synthetic"
    openstreetmap = "openstreetmap"
    csv_import = "csv_import"
    geojson_import = "geojson_import"
    other = "other"


class DataSource(Base):
    __tablename__ = "data_sources"
    __table_args__ = (
        UniqueConstraint("city_id", "name", name="uq_data_sources_city_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    city_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[DataSourceKind] = mapped_column(
        Enum(DataSourceKind, name="data_source_kind", native_enum=True),
        nullable=False,
        default=DataSourceKind.other,
    )
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    retrieval_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    license_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
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

    zones = relationship("Zone", back_populates="data_source")
    infrastructure = relationship("Infrastructure", back_populates="data_source")
    hazards = relationship("HazardObservation", back_populates="data_source")

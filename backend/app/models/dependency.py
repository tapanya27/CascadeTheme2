"""Dependency graph edges for analytical model relationships."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EdgeEvidenceKind(str, enum.Enum):
    observed = "observed"
    assumed = "assumed"
    hypothesized = "hypothesized"


class DependencyEdge(Base):
    __tablename__ = "dependency_edges"
    __table_args__ = (
        UniqueConstraint(
            "source_node",
            "target_node",
            "relationship_type",
            name="uq_dependency_edge_triplet",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_node: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target_node: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_kind: Mapped[EdgeEvidenceKind] = mapped_column(
        Enum(EdgeEvidenceKind, name="edge_evidence_kind", native_enum=True),
        nullable=False,
        default=EdgeEvidenceKind.hypothesized,
    )
    strength: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("zones.id", ondelete="SET NULL"),
        nullable=True,
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

    zone = relationship("Zone")

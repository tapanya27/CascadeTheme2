"""Operational response tasks for the Disaster Response Action Center."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ResponseTask(Base):
    """Persistent officer workflow item linked to a city/zone case."""

    __tablename__ = "response_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    city_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    zone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    why_recommended: Mapped[str] = mapped_column(Text, nullable=False, default="")
    priority: Mapped[str] = mapped_column(
        String(32), nullable=False, default="medium", server_default="medium"
    )
    # open | assigned | in_progress | blocked | done | cancelled
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="open", server_default="open", index=True
    )
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="officer", server_default="officer"
    )
    source_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    next_step: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    audit: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

"""Vulnerability assessment persistence helpers."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from app.models.assessment import VulnerabilityAssessment
from app.models.zone import Zone
from app.schemas.assessment import AssessmentOut, ComponentScoreOut


class AssessmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def to_out(self, row: VulnerabilityAssessment) -> AssessmentOut:
        zone = row.zone
        components = row.components or []
        # Normalize components to schema when stored as dicts
        parsed: list[ComponentScoreOut] | list[dict] = components
        try:
            parsed = [ComponentScoreOut.model_validate(c) for c in components]
        except Exception:  # noqa: BLE001
            parsed = components
        return AssessmentOut(
            id=row.id,
            run_id=row.run_id,
            zone_id=row.zone_id,
            zone_code=zone.code if zone else None,
            zone_name=zone.name if zone else None,
            scoring_version=row.scoring_version,
            overall_score=row.overall_score,
            category=row.category,
            confidence=row.confidence,
            components=parsed,
            weights_used=row.weights_used or {},
            reasons=list(row.reasons or []),
            data_quality=row.data_quality or {},
            limitations=list(row.limitations or []),
            source_refs=list(row.source_refs or []),
            inputs=row.inputs or {},
            explanation=row.explanation or "",
            created_at=row.created_at,
            hazard_only_score=getattr(row, "hazard_only_score", None),
            hazard_only_rank=getattr(row, "hazard_only_rank", None),
            multifactor_rank=getattr(row, "multifactor_rank", None),
            rank_uplift=getattr(row, "rank_uplift", None),
        )

    def latest_run_id(self) -> Optional[UUID]:
        row = (
            self.db.query(VulnerabilityAssessment)
            .order_by(desc(VulnerabilityAssessment.created_at))
            .first()
        )
        return row.run_id if row else None

    def latest_for_zone(self, zone_id: UUID) -> Optional[VulnerabilityAssessment]:
        return (
            self.db.query(VulnerabilityAssessment)
            .options(joinedload(VulnerabilityAssessment.zone))
            .filter(VulnerabilityAssessment.zone_id == zone_id)
            .order_by(desc(VulnerabilityAssessment.created_at))
            .first()
        )

    def latest_run_id_for_city(self, city_id: str) -> Optional[UUID]:
        row = (
            self.db.query(VulnerabilityAssessment)
            .join(Zone)
            .filter(Zone.city_id == city_id)
            .order_by(desc(VulnerabilityAssessment.created_at))
            .first()
        )
        return row.run_id if row else None

    def latest_batch(
        self, *, city_id: Optional[str] = None
    ) -> list[VulnerabilityAssessment]:
        if city_id is not None:
            run_id = self.latest_run_id_for_city(city_id)
        else:
            run_id = self.latest_run_id()
        if not run_id:
            return []
        q = (
            self.db.query(VulnerabilityAssessment)
            .options(joinedload(VulnerabilityAssessment.zone))
            .filter(VulnerabilityAssessment.run_id == run_id)
            .join(Zone)
        )
        if city_id is not None:
            q = q.filter(Zone.city_id == city_id)
        return q.order_by(Zone.code).all()

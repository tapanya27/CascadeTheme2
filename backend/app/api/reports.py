"""Disaster-report intelligence APIs — community intake to map."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.cities.deps import parse_city_id
from app.config import get_settings
from app.database import get_db
from app.ingestion.base import DataLake
from app.models.community_report import CommunityReport
from app.nlp.reports import (
    ReportIntelligence,
    enrich_empty_labels_from_keywords,
    primary_category,
    redact_pii,
    text_hash,
)
from app.security import check_rate_limit

router = APIRouter(tags=["reports"])

VERIFICATION_STATUSES = {"unverified", "verified", "rejected"}


def _intel() -> ReportIntelligence:
    return ReportIntelligence(DataLake(Path(get_settings().data_dir)).models)


class SubmitReport(BaseModel):
    text: str = Field(..., min_length=3, max_length=4000)
    lon: Optional[float] = None
    lat: Optional[float] = None
    observed_at: Optional[datetime] = None

    @model_validator(mode="after")
    def coords_together_and_in_range(self) -> "SubmitReport":
        lon, lat = self.lon, self.lat
        if (lon is None) ^ (lat is None):
            raise ValueError(
                "Provide both latitude and longitude together, or omit both. "
                "Coordinates are never inferred from report text."
            )
        if lon is not None and lat is not None:
            if not (-180.0 <= float(lon) <= 180.0):
                raise ValueError("longitude must be between -180 and 180")
            if not (-90.0 <= float(lat) <= 90.0):
                raise ValueError("latitude must be between -90 and 90")
        return self


class ReviewBody(BaseModel):
    reviewed: bool = True
    review_notes: Optional[str] = None
    disaster_related: Optional[bool] = None
    labels: Optional[list[str]] = None
    verification_status: Optional[str] = Field(
        None, description="unverified | verified | rejected"
    )


@router.post("/api/reports/train")
def train_reports(request: Request):
    check_rate_limit(request, expensive=True)
    lake = DataLake(Path(get_settings().data_dir))
    parquet = (
        lake.provider_processed("disaster_response_messages")
        / "normalized_reports.parquet"
    )
    if not parquet.exists():
        raise HTTPException(
            status_code=400,
            detail="Corpus missing. Run POST /api/ingest/reports/corpus first.",
        )
    meta = _intel().train_from_parquet(str(parquet))
    return meta


@router.post("/api/reports/submit")
def submit_report(
    body: SubmitReport,
    request: Request,
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
):
    check_rate_limit(request, expensive=True)
    intel = _intel()
    # Prefer trained model; train opportunistically if corpus exists.
    if not intel.bundle_path.exists():
        lake = DataLake(Path(get_settings().data_dir))
        parquet = (
            lake.provider_processed("disaster_response_messages")
            / "normalized_reports.parquet"
        )
        if parquet.exists():
            intel.train_from_parquet(str(parquet))

    # Redact BEFORE classify/persist. Original unredacted text is never stored.
    redacted, redaction_tags = redact_pii(body.text)
    try:
        result = intel.classify(
            redacted,
            explicit_lon=body.lon,
            explicit_lat=body.lat,
            city_id=city_id,
            observed_at=body.observed_at,
            allow_keyword_fallback=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Merge redaction tags from the pre-persist pass (classify also redacts).
    all_redactions = sorted(set(result.redactions + redaction_tags))
    category = primary_category(
        result.labels, disaster_related=result.disaster_related
    )

    # Ensure location JSON never invents coordinates; city association always set.
    location = dict(result.location or {})
    location["city_id"] = city_id
    if body.lon is None or body.lat is None:
        location.pop("lon", None)
        location.pop("lat", None)
        if result.location_precision == "coordinates":
            # Defensive — should not happen
            result.location_precision = "city"

    row = CommunityReport(
        id=uuid.uuid4(),
        city_id=city_id,
        text_redacted=redacted,
        text_hash=text_hash(redacted),
        near_duplicate_key=result.near_duplicate_key,
        disaster_related=result.disaster_related,
        disaster_related_proba=result.disaster_related_proba,
        labels=result.labels,
        label_probas=result.label_probas,
        category=category,
        needs_human_review=result.needs_human_review,
        reviewed=False,
        verification_status="unverified",
        location_precision=result.location_precision,
        location=location,
        observation_kind="unverified",
        source_reliability=result.source_reliability,
        observed_at=body.observed_at,
        provenance={
            "intake": "community_form",
            "redactions": all_redactions,
            "duplicate_of": result.duplicate_of,
            "privacy": (
                "Raw identifiers redacted before persist; "
                "original unredacted text is not stored."
            ),
            "classifier_note": (
                "NLP scores are heuristic/historical-corpus based — "
                "not claimed high real-world accuracy."
            ),
            "has_map_marker": result.location_precision == "coordinates",
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": str(row.id),
        "city_id": row.city_id,
        "category": row.category,
        "verification_status": row.verification_status,
        "needs_human_review": row.needs_human_review,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "location_precision": row.location_precision,
        "has_map_marker": row.location_precision == "coordinates",
        "classification": result.to_dict(),
        "stored_text_redacted_only": True,
        "report": _serialize(row),
        "disclaimer": (
            "Community reports default to unverified. "
            "Classifier confidence is limited; uncertain items are flagged "
            "for human review. Reports without coordinates appear in the "
            "list but not on the map."
        ),
    }


@router.get("/api/reports")
def list_reports(
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
    needs_review: Optional[bool] = None,
    with_coordinates_only: bool = Query(
        False,
        description="If true, only reports with explicit lon/lat (map markers).",
    ),
    limit: int = Query(50, ge=1, le=200),
):
    q = (
        db.query(CommunityReport)
        .filter(CommunityReport.city_id == city_id)
        .order_by(CommunityReport.created_at.desc())
    )
    if needs_review is not None:
        q = q.filter(CommunityReport.needs_human_review == needs_review)
    if with_coordinates_only:
        q = q.filter(CommunityReport.location_precision == "coordinates")
    rows = q.limit(limit).all()
    return {
        "city_id": city_id,
        "items": [_serialize(r) for r in rows],
        "total_returned": len(rows),
    }


@router.post("/api/reports/{report_id}/review")
def review_report(
    report_id: uuid.UUID,
    body: ReviewBody,
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
):
    row = (
        db.query(CommunityReport)
        .filter(
            CommunityReport.id == report_id,
            CommunityReport.city_id == city_id,
        )
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Report not found for this city")
    row.reviewed = body.reviewed
    row.review_notes = body.review_notes
    if body.disaster_related is not None:
        row.disaster_related = body.disaster_related
    if body.labels is not None:
        row.labels = body.labels
        row.category = primary_category(
            body.labels, disaster_related=row.disaster_related
        )
    if body.verification_status:
        if body.verification_status not in VERIFICATION_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"verification_status must be one of {sorted(VERIFICATION_STATUSES)}",
            )
        row.verification_status = body.verification_status
    elif body.reviewed:
        row.verification_status = "verified"
        row.needs_human_review = False
    db.commit()
    db.refresh(row)
    return _serialize(row)


def _serialize(r: CommunityReport) -> dict[str, Any]:
    loc = r.location or {}
    has_coords = (
        r.location_precision == "coordinates"
        and loc.get("lon") is not None
        and loc.get("lat") is not None
    )
    labels, category, _ = enrich_empty_labels_from_keywords(
        r.text_redacted or "",
        labels=list(r.labels or []),
        disaster_related=r.disaster_related,
    )
    return {
        "id": str(r.id),
        "city_id": r.city_id,
        "text_redacted": r.text_redacted,
        "category": category,
        "disaster_related": r.disaster_related,
        "disaster_related_proba": r.disaster_related_proba,
        "labels": labels,
        "label_probas": r.label_probas,
        "needs_human_review": r.needs_human_review,
        "reviewed": r.reviewed,
        "review_notes": r.review_notes,
        "verification_status": getattr(r, "verification_status", None)
        or "unverified",
        "location_precision": r.location_precision,
        "location": loc,
        "has_map_marker": has_coords,
        "observation_kind": r.observation_kind,
        "source_reliability": r.source_reliability,
        "observed_at": r.observed_at.isoformat() if r.observed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }

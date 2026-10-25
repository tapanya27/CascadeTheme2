"""Vulnerability assessment endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.cities.deps import parse_city_id
from app.database import get_db
from app.repositories.assessments import AssessmentRepository
from app.schemas.assessment import (
    LatestAssessmentsResponse,
    RunAssessmentsRequest,
    RunAssessmentsResponse,
)
from app.schemas.intervention import SensitivityRequest, SensitivityResponse
from app.security import check_rate_limit
from app.services.assessment_service import AssessmentService
from app.services.sensitivity_service import run_weight_sensitivity

router = APIRouter(tags=["assessments"])


@router.post("/api/assessments/run", response_model=RunAssessmentsResponse)
def run_assessments(
    request: Request,
    city_id: str = Depends(parse_city_id),
    body: RunAssessmentsRequest | None = None,
    db: Session = Depends(get_db),
) -> RunAssessmentsResponse:
    check_rate_limit(request, expensive=True)
    body = body or RunAssessmentsRequest()
    try:
        result = AssessmentService(db).run(
            zone_ids=body.zone_ids,
            weight_overrides=body.weight_overrides,
            seed_dependency_graph=body.seed_dependency_graph,
            city_id=city_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Assessment run failed. Verify PostgreSQL connectivity and zone data.",
        )

    repo = AssessmentRepository(db)
    outs = [repo.to_out(a) for a in result["assessments"]]
    return RunAssessmentsResponse(
        run_id=result["run_id"],
        scoring_version=result["scoring_version"],
        assessed=len(outs),
        assessments=outs,
        methodology=result["methodology"],
        dependency_graph_seeded=result["dependency_graph_seeded"],
        dual_rankings=result.get("dual_rankings") or [],
    )


@router.get("/api/assessments/latest", response_model=LatestAssessmentsResponse)
def latest_assessments(
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> LatestAssessmentsResponse:
    repo = AssessmentRepository(db)
    rows = repo.latest_batch(city_id=city_id)
    items = [repo.to_out(r) for r in rows]
    return LatestAssessmentsResponse(
        scoring_version=items[0].scoring_version if items else None,
        run_id=items[0].run_id if items else None,
        items=items,
        total=len(items),
    )


@router.post("/api/assessments/sensitivity", response_model=SensitivityResponse)
def assessment_sensitivity(
    request: Request,
    city_id: str = Depends(parse_city_id),
    body: SensitivityRequest | None = None,
    db: Session = Depends(get_db),
) -> SensitivityResponse:
    check_rate_limit(request, expensive=True)
    body = body or SensitivityRequest()
    try:
        result = run_weight_sensitivity(
            db,
            zone_ids=body.zone_ids,
            perturbation=body.perturbation,
            city_id=city_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Sensitivity analysis failed.",
        )
    return SensitivityResponse.model_validate(result)

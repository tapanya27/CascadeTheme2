"""Run and persist vulnerability assessments (multi-factor + hazard-only dual ranks)."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.assessment import VulnerabilityAssessment
from app.scoring.config import load_scoring_config
from app.scoring.dual_rank import compute_dual_rankings, dual_score_zone
from app.scoring.features import extract_all_zone_features
from app.services.dependency_graph import DependencyGraphService


class AssessmentService:
    def __init__(self, db: Session):
        self.db = db

    def run(
        self,
        *,
        zone_ids: Optional[list[UUID]] = None,
        weight_overrides: Optional[dict[str, float]] = None,
        seed_dependency_graph: bool = True,
        city_id: Optional[str] = None,
    ) -> dict[str, Any]:
        cfg = load_scoring_config(weight_overrides)
        run_id = uuid.uuid4()
        features_list = extract_all_zone_features(
            self.db, zone_ids, city_id=city_id
        )

        duals = [dual_score_zone(f, weight_overrides) for f in features_list]
        ranked = compute_dual_rankings(
            [
                {
                    "zone_id": d["zone_id"],
                    "zone_code": d["zone_code"],
                    "hazard_score": d["hazard_score"],
                    "multifactor_score": d["multifactor_score"],
                }
                for d in duals
            ]
        )
        rank_by_zone = {str(r["zone_id"]): r for r in ranked}

        assessments: list[VulnerabilityAssessment] = []
        for d in duals:
            multi = d["multifactor_result"]
            hazard = d["hazard_result"]
            zid = str(d["zone_id"])
            rk = rank_by_zone[zid]
            inputs = dict(multi.inputs or {})
            inputs.update(
                {
                    "view_separation": {
                        "forecast_likelihood": "see /api/early-warning (separate concept)",
                        "community_vulnerability": "multifactor_score / ranks",
                        "hazard_only_baseline": "hazard_only_score / ranks",
                        "data_quality_confidence": multi.confidence,
                    },
                    "hazard_only_score": d["hazard_score"],
                    "hazard_only_category": d["hazard_category"],
                    "hazard_only_rank": rk.get("hazard_only_rank"),
                    "multifactor_rank": rk.get("multifactor_rank"),
                    "rank_uplift": rk.get("rank_uplift"),
                    "rank_uplift_interpretation": rk.get("rank_uplift_interpretation"),
                }
            )
            row = VulnerabilityAssessment(
                id=uuid.uuid4(),
                run_id=run_id,
                zone_id=UUID(zid),
                scoring_version=result_version(multi.scoring_version),
                overall_score=multi.overall_score,
                category=multi.category,
                confidence=multi.confidence,
                components=[asdict(c) for c in multi.components],
                weights_used=multi.weights_used,
                reasons=multi.reasons,
                data_quality={
                    **multi.data_quality,
                    "hazard_only_score": d["hazard_score"],
                    "hazard_only_rank": rk.get("hazard_only_rank"),
                    "multifactor_rank": rk.get("multifactor_rank"),
                    "rank_uplift": rk.get("rank_uplift"),
                },
                limitations=list(d["limitations"]),
                source_refs=multi.source_refs,
                inputs=inputs,
                explanation=multi.narrative,
                hazard_only_score=d["hazard_score"],
                hazard_only_rank=rk.get("hazard_only_rank"),
                multifactor_rank=rk.get("multifactor_rank"),
                rank_uplift=rk.get("rank_uplift"),
            )
            # Keep mypy/runtime happy if columns not yet migrated — setattr pattern
            self.db.add(row)
            assessments.append(row)

        seeded = False
        if seed_dependency_graph:
            DependencyGraphService(self.db).ensure_default_edges()
            seeded = True

        self.db.flush()
        return {
            "run_id": run_id,
            "scoring_version": cfg.version,
            "assessments": assessments,
            "dual_rankings": ranked,
            "methodology": {
                **cfg.documentation(),
                "hazard_only_view": (
                    "Uses only flood_hazard_exposure with weights renormalized. "
                    "Separate from multi-factor vulnerability ranking."
                ),
                "rank_uplift_formula": "hazard_only_rank - multifactor_rank (rank 1 = highest priority)",
                "non_causal_note": (
                    "Rank uplift is a prioritisation difference, not a causal effect."
                ),
            },
            "dependency_graph_seeded": seeded,
        }


def result_version(base: str) -> str:
    if "dual" in base:
        return base
    return f"{base}+dual-rank"

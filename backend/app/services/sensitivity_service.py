"""
Weight sensitivity analysis for the transparent heuristic scorer.

This is NOT model validation or cross-validated predictive performance.
It shows whether high-priority zone rankings change when configurable
weights are perturbed.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.scoring.config import default_scoring_config, load_scoring_config
from app.scoring.engine import score_zone_features
from app.scoring.features import extract_all_zone_features


def run_weight_sensitivity(
    db: Session,
    *,
    zone_ids: Optional[list[UUID]] = None,
    perturbation: float = 0.2,
    city_id: Optional[str] = None,
) -> dict[str, Any]:
    if perturbation <= 0 or perturbation >= 1:
        raise ValueError("perturbation must be in (0, 1)")

    base_cfg = default_scoring_config()
    features_list = extract_all_zone_features(db, zone_ids, city_id=city_id)
    if not features_list:
        return {
            "method": "weight_perturbation_heuristic",
            "disclaimer": (
                "No zones available for sensitivity analysis. "
                "This is not predictive-model validation."
            ),
            "baseline_ranking": [],
            "variants": [],
        }

    def rank(weight_overrides: Optional[dict[str, float]] = None) -> list[dict[str, Any]]:
        cfg = load_scoring_config(weight_overrides)
        rows = []
        for feat in features_list:
            result = score_zone_features(feat, cfg)
            rows.append(
                {
                    "zone_id": feat["zone_id"],
                    "zone_code": feat["zone_code"],
                    "zone_name": feat["zone_name"],
                    "overall_score": result.overall_score,
                    "category": result.category,
                }
            )
        rows.sort(
            key=lambda r: (
                float("inf") if r["overall_score"] is None else -float(r["overall_score"])
            )
        )
        return rows

    baseline = rank(None)
    baseline_top = [r["zone_code"] for r in baseline[:3]]

    variants = []
    for comp in base_cfg.components:
        if comp.weight <= 0:
            continue
        up = dict(base_cfg.weight_map())
        up[comp.key] = comp.weight * (1.0 + perturbation)
        down = dict(base_cfg.weight_map())
        down[comp.key] = max(comp.weight * (1.0 - perturbation), 1e-6)

        for label, weights in ((f"{comp.key}_up", up), (f"{comp.key}_down", down)):
            ranked = rank(weights)
            top = [r["zone_code"] for r in ranked[:3]]
            variants.append(
                {
                    "variant": label,
                    "weights": weights,
                    "top_zone_codes": top,
                    "top3_changed": top != baseline_top,
                }
            )

    changed = sum(1 for v in variants if v["top3_changed"])
    return {
        "method": "weight_perturbation_heuristic",
        "perturbation": perturbation,
        "disclaimer": (
            "Sensitivity of a transparent weighted heuristic under weight perturbations. "
            "Not trained-model validation, cross-validation, or claimed predictive accuracy."
        ),
        "assumptions": [
            f"Each component weight is scaled by ±{perturbation:.0%} in isolation.",
            "Missing components remain unavailable (not zero-filled).",
            "Rankings use overall_score descending (higher = more vulnerable in this model).",
        ],
        "baseline_ranking": baseline,
        "baseline_top3": baseline_top,
        "variants": variants,
        "summary": {
            "variants_tested": len(variants),
            "variants_with_top3_change": changed,
            "interpretation": (
                "If many variants change the top-3, priority lists are sensitive to "
                "weight choices; treat rankings as exploratory."
                if changed
                else "Top-3 priorities were stable under the tested weight perturbations."
            ),
        },
    }

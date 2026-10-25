"""Hazard-only vs multi-factor rankings and hidden-community rank uplift."""

from __future__ import annotations

from typing import Any, Optional

from app.scoring.config import ScoringConfig, default_scoring_config, load_scoring_config
from app.scoring.engine import ComponentInput, ScoreResult, combine_components, score_zone_features


def score_hazard_only(
    features: dict[str, Any],
    config: Optional[ScoringConfig] = None,
) -> ScoreResult:
    """Baseline using only flood_hazard_exposure (renormalized to weight 1.0)."""
    cfg = config or default_scoring_config()
    # Build a config with only flood component weight > 0
    hazard_cfg = cfg.with_weights(
        {
            "flood_hazard_exposure": 1.0,
            "population_exposure": 0.0,
            "road_disruption_risk": 0.0,
            "healthcare_travel_burden": 0.0,
            "infrastructure_availability": 0.0,
        }
    )
    # with_weights allows 0; combine_components skips zero effective via available_weight
    # But unavailable non-flood still skipped. Force only flood input path:
    full = score_zone_features(features, cfg)
    flood_input = None
    for c in full.components:
        if c.key == "flood_hazard_exposure":
            flood_input = ComponentInput(
                key=c.key,
                raw_value=c.raw_value,
                status=c.status if c.status != "synthetic" else "synthetic",
                is_synthetic=c.is_synthetic,
                source_refs=list(c.source_refs),
                notes="Hazard-only baseline view",
            )
            break
    if flood_input is None:
        flood_input = ComponentInput(
            key="flood_hazard_exposure",
            raw_value=None,
            status="unavailable",
            notes="No flood component",
        )
    # Pass only flood as available by zeroing others as unavailable
    inputs = [
        flood_input,
        ComponentInput("population_exposure", None, "unavailable"),
        ComponentInput("road_disruption_risk", None, "unavailable"),
        ComponentInput("healthcare_travel_burden", None, "unavailable"),
        ComponentInput("infrastructure_availability", None, "unavailable"),
    ]
    # Use weights where only flood > 0
    result = combine_components(
        inputs,
        hazard_cfg,
        zone_label=str(features.get("zone_name") or features.get("zone_code") or "Zone"),
        extra_inputs={"view": "hazard_only", **(features if isinstance(features, dict) else {})},
    )
    return result


def compute_dual_rankings(
    zone_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    zone_results items must include:
      zone_id, zone_code, hazard_score, multifactor_score
    Scores may be None (unscored) — those get null ranks.
    Rank 1 = highest priority (highest score among scored zones).
    rank_uplift = hazard_only_rank - multifactor_rank
    Positive uplift => zone moved UP in priority under multi-factor view.
    """
    scored_h = [z for z in zone_results if z.get("hazard_score") is not None]
    scored_m = [z for z in zone_results if z.get("multifactor_score") is not None]

    def _ranks(items: list[dict[str, Any]], score_key: str) -> dict[str, int]:
        ordered = sorted(items, key=lambda z: (-float(z[score_key]), str(z.get("zone_code") or "")))
        return {str(z["zone_id"]): i + 1 for i, z in enumerate(ordered)}

    h_rank = _ranks(scored_h, "hazard_score")
    m_rank = _ranks(scored_m, "multifactor_score")

    out: list[dict[str, Any]] = []
    for z in zone_results:
        zid = str(z["zone_id"])
        hr = h_rank.get(zid)
        mr = m_rank.get(zid)
        uplift = None
        if hr is not None and mr is not None:
            uplift = hr - mr
        out.append(
            {
                **z,
                "hazard_only_rank": hr,
                "multifactor_rank": mr,
                "rank_uplift": uplift,
                "rank_uplift_interpretation": (
                    None
                    if uplift is None
                    else (
                        "Moved up in priority vs hazard-only"
                        if uplift > 0
                        else (
                            "Moved down in priority vs hazard-only"
                            if uplift < 0
                            else "Same rank as hazard-only"
                        )
                    )
                ),
                "note": (
                    "Rank uplift is a prioritisation difference, not a causal effect. "
                    "Confidence remains a data-coverage heuristic, not calibrated uncertainty."
                ),
            }
        )
    return out


def dual_score_zone(
    features: dict[str, Any],
    weight_overrides: Optional[dict[str, float]] = None,
) -> dict[str, Any]:
    cfg = load_scoring_config(weight_overrides)
    multi = score_zone_features(features, cfg)
    hazard = score_hazard_only(features, cfg)
    return {
        "zone_id": features.get("zone_id"),
        "zone_code": features.get("zone_code"),
        "zone_name": features.get("zone_name"),
        "hazard_score": hazard.overall_score,
        "hazard_category": hazard.category,
        "hazard_components": [c.__dict__ for c in hazard.components],
        "multifactor_score": multi.overall_score,
        "multifactor_category": multi.category,
        "multifactor_components": [c.__dict__ for c in multi.components],
        "multifactor_result": multi,
        "hazard_result": hazard,
        "confidence": multi.confidence,
        "data_quality": multi.data_quality,
        "source_refs": multi.source_refs,
        "reasons": multi.reasons,
        "limitations": multi.limitations + [
            "hazard_only and multifactor are separate views; forecast likelihood is separate.",
        ],
        "explanation": multi.narrative,
        "scoring_version": multi.scoring_version,
        "weights_used": multi.weights_used,
        "inputs": multi.inputs,
    }

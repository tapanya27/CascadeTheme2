"""
Intervention scenario comparison (Module 4).

Outputs are modeled simulations using the transparent scoring heuristic —
NOT guaranteed real-world outcomes. Costs, budgets, capacity, and travel
times are never invented; required quantitative assumptions must be supplied
by the caller or the scenario is rejected.
"""

from __future__ import annotations

import copy
import math
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.models.intervention import InterventionScenario, InterventionType
from app.models.zone import Zone
from app.scoring.config import load_scoring_config
from app.scoring.engine import score_zone_features
from app.scoring.features import extract_zone_features

SIMULATION_DISCLAIMER = (
    "Scenario outputs are simulations based on a transparent weighted heuristic — "
    "not guaranteed real-world outcomes, and not a trained predictive model."
)


class InterventionEvaluationError(ValueError):
    """Raised when a scenario cannot be evaluated with available inputs."""


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _zone_centroid_approx(db: Session, zone: Zone) -> tuple[float, float]:
    """Return (lon, lat) from zone properties or PostGIS ST_Centroid — never another city."""
    props = zone.properties or {}
    if "centroid_lon" in props and "centroid_lat" in props:
        return float(props["centroid_lon"]), float(props["centroid_lat"])
    from sqlalchemy import text

    row = db.execute(
        text(
            "SELECT ST_X(ST_Centroid(boundary)) AS lon, "
            "ST_Y(ST_Centroid(boundary)) AS lat FROM zones WHERE id = :zid"
        ),
        {"zid": str(zone.id)},
    ).mappings().first()
    if row and row["lon"] is not None and row["lat"] is not None:
        return float(row["lon"]), float(row["lat"])
    raise InterventionEvaluationError(
        f"Cannot derive centroid for zone {zone.code} in city {zone.city_id}"
    )


def score_snapshot(features: dict[str, Any], weight_overrides: Optional[dict] = None) -> dict:
    cfg = load_scoring_config(weight_overrides)
    result = score_zone_features(features, cfg)
    return result.to_dict()


def apply_intervention(
    baseline_features: dict[str, Any],
    intervention_type: InterventionType,
    params: dict[str, Any],
    *,
    centroid: tuple[float, float],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """
    Return (modified_features, assumptions, limitations).
    Raises InterventionEvaluationError if required inputs are missing.
    """
    features = copy.deepcopy(baseline_features)
    assumptions: list[str] = []
    limitations: list[str] = [SIMULATION_DISCLAIMER]

    if intervention_type == InterventionType.place_temporary_resource:
        lon = params.get("lon")
        lat = params.get("lat")
        if lon is None or lat is None:
            raise InterventionEvaluationError(
                "place_temporary_resource requires lon and lat for the proposed resource."
            )
        try:
            lon_f, lat_f = float(lon), float(lat)
        except (TypeError, ValueError) as exc:
            raise InterventionEvaluationError("lon/lat must be numeric") from exc
        if not (-180 <= lon_f <= 180 and -90 <= lat_f <= 90):
            raise InterventionEvaluationError("lon/lat out of valid geographic range")

        dist = _haversine_km(centroid[0], centroid[1], lon_f, lat_f)
        current = features.get("nearest_healthcare_km")
        new_dist = dist if current is None else min(float(current), dist)
        features["nearest_healthcare_km"] = round(new_dist, 4)
        features["healthcare_status"] = "available"
        features["healthcare_is_synthetic"] = True
        features["healthcare_notes"] = (
            f"Hypothetical temporary resource at ({lon_f},{lat_f}); "
            f"modeled great-circle distance from zone centroid ≈ {dist:.2f} km."
        )
        features["healthcare_sources"] = ["hypothetical_intervention"]
        fac = int(features.get("facility_count") or 0)
        features["facility_count"] = fac + 1
        features["facility_status"] = "available"
        features["facility_is_synthetic"] = True
        features["facility_notes"] = (
            "Facility count includes one hypothetical temporary emergency resource."
        )
        assumptions.append(
            "Temporary resource is assumed reachable via great-circle distance from "
            "zone centroid; no road network, staffing, or capacity is modeled."
        )
        limitations.append(
            "No costs, budgets, or effectiveness rates are invented. "
            "Distance is geometric, not travel time."
        )
        return features, assumptions, limitations

    if intervention_type == InterventionType.accessibility_improvement:
        # Prefer explicit assumed distance OR placement coords — never invent
        if params.get("lon") is not None and params.get("lat") is not None:
            return apply_intervention(
                baseline_features,
                InterventionType.place_temporary_resource,
                params,
                centroid=centroid,
            )
        assumed = params.get("assumed_nearest_healthcare_km")
        if assumed is None:
            raise InterventionEvaluationError(
                "accessibility_improvement requires either lon/lat for a proposed "
                "facility OR assumed_nearest_healthcare_km supplied by the user. "
                "Travel times are not invented."
            )
        try:
            assumed_f = float(assumed)
        except (TypeError, ValueError) as exc:
            raise InterventionEvaluationError(
                "assumed_nearest_healthcare_km must be numeric"
            ) from exc
        if assumed_f < 0 or assumed_f > 100:
            raise InterventionEvaluationError(
                "assumed_nearest_healthcare_km must be between 0 and 100"
            )
        features["nearest_healthcare_km"] = assumed_f
        features["healthcare_status"] = "available"
        features["healthcare_is_synthetic"] = True
        features["healthcare_notes"] = (
            f"User-supplied assumed nearest healthcare distance: {assumed_f} km "
            "(not measured travel time)."
        )
        features["healthcare_sources"] = ["user_assumption"]
        assumptions.append(
            f"Caller supplied assumed_nearest_healthcare_km={assumed_f} as a "
            "hypothetical accessibility improvement."
        )
        limitations.append(
            "This scenario uses a user-provided distance assumption; it is not "
            "derived from road routing or ambulance ETA data."
        )
        return features, assumptions, limitations

    if intervention_type == InterventionType.alternative_emergency_route:
        # Require explicit post-intervention disruption index OR relative reduction
        if params.get("assumed_road_disruption_index") is not None:
            try:
                new_idx = float(params["assumed_road_disruption_index"])
            except (TypeError, ValueError) as exc:
                raise InterventionEvaluationError(
                    "assumed_road_disruption_index must be numeric"
                ) from exc
            if new_idx < 0 or new_idx > 50:
                raise InterventionEvaluationError(
                    "assumed_road_disruption_index out of accepted range [0, 50]"
                )
            features["road_disruption_index"] = new_idx
            assumptions.append(
                f"Caller supplied assumed_road_disruption_index={new_idx} for an "
                "alternative emergency route hypothesis."
            )
        elif params.get("assumed_relative_reduction") is not None:
            try:
                red = float(params["assumed_relative_reduction"])
            except (TypeError, ValueError) as exc:
                raise InterventionEvaluationError(
                    "assumed_relative_reduction must be numeric"
                ) from exc
            if not (0 <= red <= 1):
                raise InterventionEvaluationError(
                    "assumed_relative_reduction must be in [0, 1]"
                )
            current = features.get("road_disruption_index")
            if current is None:
                raise InterventionEvaluationError(
                    "Cannot apply relative road-disruption reduction: baseline "
                    "road_disruption_index is unavailable for this zone."
                )
            features["road_disruption_index"] = round(float(current) * (1.0 - red), 4)
            assumptions.append(
                f"Caller assumed a {red:.0%} relative reduction in the modeled "
                "road disruption index (not observed traffic data)."
            )
        else:
            raise InterventionEvaluationError(
                "alternative_emergency_route requires assumed_road_disruption_index "
                "or assumed_relative_reduction. Route travel times are not invented."
            )
        features["road_status"] = "available"
        features["road_is_synthetic"] = True
        features["road_notes"] = (
            "Road disruption index after hypothetical alternative route (user assumption)."
        )
        features["road_sources"] = ["user_assumption"]
        limitations.append(
            "No travel-time savings or construction costs are invented. "
            "Only the modeled disruption proxy changes under stated assumptions."
        )
        return features, assumptions, limitations

    if intervention_type == InterventionType.compare_resource_placements:
        opts = params.get("placements")
        if not isinstance(opts, list) or len(opts) < 2:
            raise InterventionEvaluationError(
                "compare_resource_placements requires placements: [{lon,lat,label?}, ...] "
                "with at least two options."
            )
        # Evaluation of multi-option comparison is handled by the service layer
        raise InterventionEvaluationError(
            "compare_resource_placements is handled as a multi-option compare; "
            "use InterventionService.compare_placements."
        )

    raise InterventionEvaluationError(f"Unsupported intervention type: {intervention_type}")


class InterventionService:
    def __init__(self, db: Session):
        self.db = db

    def list_catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "type": InterventionType.place_temporary_resource.value,
                "label": "Temporary emergency-resource placement",
                "required": ["lon", "lat"],
                "optional": ["name", "notes"],
                "evaluable_when": "Zone has a usable centroid approximation",
                "description": (
                    "Places a hypothetical temporary resource and re-scores "
                    "healthcare distance + facility availability components."
                ),
            },
            {
                "type": InterventionType.accessibility_improvement.value,
                "label": "Emergency facility accessibility improvement",
                "required_one_of": [["lon", "lat"], ["assumed_nearest_healthcare_km"]],
                "description": (
                    "Either place a facility (lon/lat) or supply an assumed post-intervention "
                    "nearest distance in km. Travel times are never invented."
                ),
            },
            {
                "type": InterventionType.alternative_emergency_route.value,
                "label": "Alternative emergency route (disruption proxy)",
                "required_one_of": [
                    ["assumed_road_disruption_index"],
                    ["assumed_relative_reduction"],
                ],
                "evaluable_when": (
                    "Relative reduction requires baseline road_disruption_index"
                ),
                "description": (
                    "Adjusts the modeled road-disruption proxy under explicit user assumptions."
                ),
            },
            {
                "type": InterventionType.compare_resource_placements.value,
                "label": "Compare resource-allocation placements",
                "required": ["placements"],
                "description": (
                    "Compare two or more hypothetical placements by modeled distance "
                    "and resulting vulnerability score."
                ),
            },
        ]

    def compare(
        self,
        *,
        zone_id: UUID,
        intervention_type: InterventionType,
        name: str,
        params: dict[str, Any],
        weight_overrides: Optional[dict[str, float]] = None,
        notes: Optional[str] = None,
        persist: bool = True,
        city_id: Optional[str] = None,
    ) -> InterventionScenario | dict[str, Any]:
        q = (
            self.db.query(Zone)
            .options(joinedload(Zone.data_source))
            .filter(Zone.id == zone_id)
        )
        if city_id is not None:
            q = q.filter(Zone.city_id == city_id)
        zone = q.one_or_none()
        if not zone:
            raise InterventionEvaluationError(
                "Zone not found for the selected city "
                "(scenarios cannot cross city boundaries)"
            )

        baseline_features = extract_zone_features(self.db, zone)
        centroid = _zone_centroid_approx(self.db, zone)
        if (zone.properties or {}).get("centroid_lon"):
            centroid_assumption = "Zone centroid taken from zone properties."
        else:
            centroid_assumption = (
                f"Zone centroid from PostGIS ST_Centroid for city_id={zone.city_id} "
                "(great-circle distances are approximate, not travel time)."
            )

        baseline_score = score_snapshot(baseline_features, weight_overrides)

        if intervention_type == InterventionType.compare_resource_placements:
            payload = self._compare_placements(
                baseline_features=baseline_features,
                baseline_score=baseline_score,
                params=params,
                centroid=centroid,
                weight_overrides=weight_overrides,
                centroid_assumption=centroid_assumption,
            )
        else:
            modified, assumptions, limitations = apply_intervention(
                baseline_features,
                intervention_type,
                params,
                centroid=centroid,
            )
            assumptions = [centroid_assumption, *assumptions]
            after = score_snapshot(modified, weight_overrides)
            payload = self._build_payload(
                intervention_type=intervention_type,
                baseline_features=baseline_features,
                baseline_score=baseline_score,
                after_features=modified,
                after_score=after,
                assumptions=assumptions,
                limitations=limitations,
                params=params,
            )

        cfg = load_scoring_config(weight_overrides)
        row = InterventionScenario(
            id=uuid.uuid4(),
            zone_id=zone_id,
            name=name,
            intervention_type=intervention_type,
            scoring_version=cfg.version,
            assumptions={"items": payload["assumptions"]},
            inputs=params,
            baseline=payload["baseline"],
            results=payload["results"],
            limitations=payload["limitations"],
            provenance={
                "zone_code": zone.code,
                "zone_is_synthetic": bool(
                    zone.data_source.is_synthetic if zone.data_source else False
                ),
                "simulated": True,
                "disclaimer": SIMULATION_DISCLAIMER,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            notes=notes,
        )
        if persist:
            self.db.add(row)
            self.db.flush()
            return row
        return {
            "id": None,
            "zone_id": str(zone_id),
            "name": name,
            "intervention_type": intervention_type.value,
            "scoring_version": cfg.version,
            **payload,
            "provenance": row.provenance,
        }

    def _compare_placements(
        self,
        *,
        baseline_features: dict[str, Any],
        baseline_score: dict[str, Any],
        params: dict[str, Any],
        centroid: tuple[float, float],
        weight_overrides: Optional[dict[str, float]],
        centroid_assumption: str,
    ) -> dict[str, Any]:
        placements = params.get("placements")
        if not isinstance(placements, list) or len(placements) < 2:
            raise InterventionEvaluationError(
                "placements must be a list of at least two {lon, lat, label?} objects"
            )
        options = []
        for i, p in enumerate(placements):
            if not isinstance(p, dict):
                raise InterventionEvaluationError("Each placement must be an object")
            feat, assumptions, limitations = apply_intervention(
                baseline_features,
                InterventionType.place_temporary_resource,
                p,
                centroid=centroid,
            )
            score = score_snapshot(feat, weight_overrides)
            options.append(
                {
                    "label": p.get("label") or f"Option {i + 1}",
                    "lon": p.get("lon"),
                    "lat": p.get("lat"),
                    "score": score,
                    "nearest_healthcare_km": feat.get("nearest_healthcare_km"),
                    "assumptions": assumptions,
                    "limitations": limitations,
                }
            )
        # Rank by overall_score ascending (lower vulnerability better for intervention)
        ranked = sorted(
            options,
            key=lambda o: (
                float("inf")
                if o["score"].get("overall_score") is None
                else float(o["score"]["overall_score"])
            ),
        )
        return {
            "assumptions": [
                centroid_assumption,
                "Each placement is evaluated independently as a temporary resource.",
                "No budgets or capacity constraints are invented.",
            ],
            "limitations": [
                SIMULATION_DISCLAIMER,
                "Comparison uses modeled scores only; it does not recommend operational decisions.",
            ],
            "baseline": {
                "features": {
                    k: baseline_features.get(k)
                    for k in (
                        "nearest_healthcare_km",
                        "road_disruption_index",
                        "facility_count",
                        "flood_severity_score",
                    )
                },
                "score": baseline_score,
            },
            "results": {
                "kind": "multi_option",
                "options": ranked,
                "preferred_label": ranked[0]["label"] if ranked else None,
                "delta_vs_baseline": [
                    {
                        "label": o["label"],
                        "score_delta": (
                            None
                            if baseline_score.get("overall_score") is None
                            or o["score"].get("overall_score") is None
                            else round(
                                float(o["score"]["overall_score"])
                                - float(baseline_score["overall_score"]),
                                2,
                            )
                        ),
                    }
                    for o in ranked
                ],
            },
        }

    def _build_payload(
        self,
        *,
        intervention_type: InterventionType,
        baseline_features: dict[str, Any],
        baseline_score: dict[str, Any],
        after_features: dict[str, Any],
        after_score: dict[str, Any],
        assumptions: list[str],
        limitations: list[str],
        params: dict[str, Any],
    ) -> dict[str, Any]:
        b_overall = baseline_score.get("overall_score")
        a_overall = after_score.get("overall_score")
        component_deltas = []
        base_comps = {
            c["key"]: c for c in baseline_score.get("components") or [] if isinstance(c, dict)
        }
        for c in after_score.get("components") or []:
            if not isinstance(c, dict):
                continue
            before = base_comps.get(c["key"], {})
            component_deltas.append(
                {
                    "key": c["key"],
                    "label": c.get("label"),
                    "before_normalized": before.get("normalized_score"),
                    "after_normalized": c.get("normalized_score"),
                    "before_contribution": before.get("contribution"),
                    "after_contribution": c.get("contribution"),
                }
            )
        tradeoffs = {}
        if (
            baseline_features.get("nearest_healthcare_km") is not None
            and after_features.get("nearest_healthcare_km") is not None
        ):
            tradeoffs["nearest_healthcare_km"] = {
                "before": baseline_features["nearest_healthcare_km"],
                "after": after_features["nearest_healthcare_km"],
                "delta_km": round(
                    float(after_features["nearest_healthcare_km"])
                    - float(baseline_features["nearest_healthcare_km"]),
                    4,
                ),
            }
        if (
            baseline_features.get("road_disruption_index") is not None
            and after_features.get("road_disruption_index") is not None
        ):
            tradeoffs["road_disruption_index"] = {
                "before": baseline_features["road_disruption_index"],
                "after": after_features["road_disruption_index"],
                "delta": round(
                    float(after_features["road_disruption_index"])
                    - float(baseline_features["road_disruption_index"]),
                    4,
                ),
            }

        return {
            "assumptions": assumptions,
            "limitations": limitations,
            "baseline": {
                "features": {
                    k: baseline_features.get(k)
                    for k in (
                        "nearest_healthcare_km",
                        "road_disruption_index",
                        "facility_count",
                        "flood_severity_score",
                    )
                },
                "score": baseline_score,
            },
            "results": {
                "kind": "single",
                "intervention_type": intervention_type.value,
                "params": params,
                "after_features": {
                    k: after_features.get(k)
                    for k in (
                        "nearest_healthcare_km",
                        "road_disruption_index",
                        "facility_count",
                        "flood_severity_score",
                    )
                },
                "after_score": after_score,
                "overall_score_delta": (
                    None
                    if b_overall is None or a_overall is None
                    else round(float(a_overall) - float(b_overall), 2)
                ),
                "component_deltas": component_deltas,
                "tradeoffs": tradeoffs,
                "data_quality_after": after_score.get("data_quality"),
            },
        }

    def list_scenarios(
        self,
        zone_id: Optional[UUID] = None,
        limit: int = 50,
        *,
        city_id: Optional[str] = None,
    ) -> list[InterventionScenario]:
        q = self.db.query(InterventionScenario).options(
            joinedload(InterventionScenario.zone)
        )
        if city_id is not None:
            q = q.join(Zone).filter(Zone.city_id == city_id)
        if zone_id:
            q = q.filter(InterventionScenario.zone_id == zone_id)
        return q.order_by(InterventionScenario.created_at.desc()).limit(limit).all()

    def get(
        self, scenario_id: UUID, *, city_id: Optional[str] = None
    ) -> Optional[InterventionScenario]:
        q = (
            self.db.query(InterventionScenario)
            .options(joinedload(InterventionScenario.zone))
            .filter(InterventionScenario.id == scenario_id)
        )
        if city_id is not None:
            q = q.join(Zone).filter(Zone.city_id == city_id)
        return q.one_or_none()

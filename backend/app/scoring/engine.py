"""Pure vulnerability scoring functions (no DB I/O)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from app.scoring.config import (
    ComponentDefinition,
    ComponentStatus,
    ScoringConfig,
    default_scoring_config,
)


@dataclass
class ComponentInput:
    key: str
    raw_value: Optional[float]
    status: ComponentStatus
    is_synthetic: bool = False
    source_refs: list[str] = field(default_factory=list)
    notes: Optional[str] = None


@dataclass
class ComponentScore:
    key: str
    label: str
    status: ComponentStatus
    raw_value: Optional[float]
    normalized_score: Optional[float]  # 0–100 vulnerability contribution
    weight_configured: float
    weight_effective: float  # after renormalization among available
    direction: str
    is_synthetic: bool
    contribution: Optional[float]  # weight_effective * normalized
    reason: str
    source_refs: list[str] = field(default_factory=list)
    limitations: str = ""


@dataclass
class ScoreResult:
    overall_score: Optional[float]
    category: Optional[str]
    components: list[ComponentScore]
    reasons: list[str]
    data_quality: dict[str, Any]
    confidence: float
    limitations: list[str]
    source_refs: list[str]
    scoring_version: str
    weights_used: dict[str, float]
    narrative: str
    inputs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "category": self.category,
            "components": [asdict(c) for c in self.components],
            "reasons": self.reasons,
            "data_quality": self.data_quality,
            "confidence": self.confidence,
            "limitations": self.limitations,
            "source_refs": self.source_refs,
            "scoring_version": self.scoring_version,
            "weights_used": self.weights_used,
            "narrative": self.narrative,
            "inputs": self.inputs,
        }


def normalize_linear(
    raw: float,
    raw_min: float,
    raw_max: float,
    *,
    invert: bool = False,
) -> float:
    """Map raw to 0–100. Invert when higher raw means lower vulnerability."""
    if raw_max == raw_min:
        raise ValueError("raw_max must differ from raw_min")
    clamped = max(raw_min, min(raw_max, float(raw)))
    ratio = (clamped - raw_min) / (raw_max - raw_min)
    score = (1.0 - ratio) * 100.0 if invert else ratio * 100.0
    return round(max(0.0, min(100.0, score)), 4)


def categorize(score: float, config: Optional[ScoringConfig] = None) -> str:
    cfg = config or default_scoring_config()
    s = float(score)
    for t in cfg.categories:
        if t.min_inclusive <= s < t.max_exclusive:
            return t.category
    if s >= 100:
        return "critical"
    raise ValueError(f"Score {score} outside documented category thresholds")


def combine_components(
    inputs: list[ComponentInput],
    config: Optional[ScoringConfig] = None,
    *,
    zone_label: str = "Zone",
    extra_inputs: Optional[dict[str, Any]] = None,
) -> ScoreResult:
    """
    Combine component inputs into an overall score.

    Unavailable components are excluded; remaining weights renormalized.
    Synthetic available values are included but reduce confidence.
    """
    cfg = config or default_scoring_config()
    by_key = {i.key: i for i in inputs}
    component_scores: list[ComponentScore] = []
    available_weight = 0.0

    def _is_scorable(inp: ComponentInput) -> bool:
        return (
            inp.status in {"available", "synthetic"}
            and inp.raw_value is not None
        )

    for defn in cfg.components:
        inp = by_key.get(defn.key)
        if inp is None:
            inp = ComponentInput(
                key=defn.key,
                raw_value=None,
                status="unavailable",
                notes="No input provided for this component",
            )
        if _is_scorable(inp) and defn.weight > 0:
            available_weight += defn.weight

    if available_weight <= 0:
        return ScoreResult(
            overall_score=None,
            category=None,
            components=[
                _unavailable_score(defn, by_key.get(defn.key))
                for defn in cfg.components
            ],
            reasons=["No scorable components available; overall score withheld."],
            data_quality={
                "components_configured": len(cfg.components),
                "components_available": 0,
                "components_unavailable": len(cfg.components),
                "components_synthetic": 0,
                "weight_coverage": 0.0,
            },
            confidence=0.0,
            limitations=[
                cfg.disclaimer,
                "Overall score not computed because every component was unavailable.",
            ],
            source_refs=[],
            scoring_version=cfg.version,
            weights_used=cfg.weight_map(),
            narrative=(
                f"{zone_label}: vulnerability score could not be computed because "
                "required input components were unavailable. Missing data was not "
                "replaced with zeros."
            ),
            inputs=extra_inputs or {},
        )

    reasons: list[str] = []
    source_refs: list[str] = []
    synth_count = 0
    avail_count = 0
    unavail_count = 0
    weighted_sum = 0.0

    for defn in cfg.components:
        inp = by_key.get(defn.key) or ComponentInput(
            key=defn.key, raw_value=None, status="unavailable"
        )
        effective = (
            (defn.weight / available_weight)
            if (_is_scorable(inp) and defn.weight > 0)
            else 0.0
        )

        if not _is_scorable(inp):
            unavail_count += 1
            component_scores.append(
                ComponentScore(
                    key=defn.key,
                    label=defn.label,
                    status="unavailable",
                    raw_value=None,
                    normalized_score=None,
                    weight_configured=defn.weight,
                    weight_effective=0.0,
                    direction=defn.direction,
                    is_synthetic=False,
                    contribution=None,
                    reason=(
                        inp.notes
                        or f"{defn.label} unavailable — excluded from weighted score "
                        "(not imputed)."
                    ),
                    source_refs=inp.source_refs,
                    limitations=defn.limitations,
                )
            )
            reasons.append(f"{defn.label}: unavailable (excluded, not imputed).")
            continue

        avail_count += 1
        invert = defn.direction == "higher_better"
        try:
            norm = normalize_linear(
                float(inp.raw_value),
                defn.raw_min,
                defn.raw_max,
                invert=invert,
            )
        except ValueError as exc:
            raise ValueError(f"Cannot normalize {defn.key}: {exc}") from exc

        contrib = round(effective * norm, 4)
        weighted_sum += contrib
        if inp.is_synthetic or inp.status == "synthetic":
            synth_count += 1
            is_synth = True
            status: ComponentStatus = "synthetic"
        else:
            is_synth = False
            status = "available"

        reason = _component_reason(defn, float(inp.raw_value), norm, effective, is_synth)
        if inp.notes:
            reason = f"{reason} {inp.notes}"
        reasons.append(reason)
        source_refs.extend(inp.source_refs)

        component_scores.append(
            ComponentScore(
                key=defn.key,
                label=defn.label,
                status=status,
                raw_value=float(inp.raw_value),
                normalized_score=norm,
                weight_configured=defn.weight,
                weight_effective=round(effective, 6),
                direction=defn.direction,
                is_synthetic=is_synth,
                contribution=contrib,
                reason=reason,
                source_refs=list(inp.source_refs),
                limitations=defn.limitations,
            )
        )

    overall = round(weighted_sum, 2)
    category = categorize(overall, cfg)
    configured_weight = sum(c.weight for c in cfg.components)
    weight_coverage = (
        available_weight / configured_weight if configured_weight else 0.0
    )
    # Confidence: coverage of configured weight, penalize synthetic share
    synth_share = synth_count / avail_count if avail_count else 1.0
    confidence = round(max(0.0, min(1.0, weight_coverage * (1.0 - 0.5 * synth_share))), 3)

    limitations = [
        cfg.disclaimer,
        "Category thresholds are relative to this scoring configuration only.",
    ]
    if synth_count:
        limitations.append(
            f"{synth_count} component(s) used clearly marked synthetic demonstration values."
        )
    if unavail_count:
        limitations.append(
            f"{unavail_count} component(s) unavailable; weights renormalized among available."
        )

    narrative = _narrative(zone_label, overall, category, component_scores, confidence)

    return ScoreResult(
        overall_score=overall,
        category=category,
        components=component_scores,
        reasons=reasons,
        data_quality={
            "components_configured": len(cfg.components),
            "components_available": avail_count,
            "components_unavailable": unavail_count,
            "components_synthetic": synth_count,
            "weight_coverage": round(weight_coverage, 4),
            "weights_renormalized": True,
        },
        confidence=confidence,
        limitations=limitations,
        source_refs=sorted(set(source_refs)),
        scoring_version=cfg.version,
        weights_used={c.key: c.weight_effective for c in component_scores},
        narrative=narrative,
        inputs=extra_inputs or {},
    )


def score_zone_features(
    features: dict[str, Any],
    config: Optional[ScoringConfig] = None,
) -> ScoreResult:
    """Map extracted feature dict → ScoreResult."""
    cfg = config or default_scoring_config()
    zone_label = str(features.get("zone_name") or features.get("zone_code") or "Zone")
    inputs: list[ComponentInput] = []

    # Flood
    flood_raw = features.get("flood_severity_score")
    flood_status = features.get("flood_status", "unavailable")
    inputs.append(
        ComponentInput(
            key="flood_hazard_exposure",
            raw_value=float(flood_raw) if flood_raw is not None else None,
            status=flood_status,
            is_synthetic=bool(features.get("flood_is_synthetic")),
            source_refs=list(features.get("flood_sources") or []),
            notes=features.get("flood_notes"),
        )
    )

    # Population — never invent; only if present
    pop = features.get("population")
    if pop is None:
        inputs.append(
            ComponentInput(
                key="population_exposure",
                raw_value=None,
                status="unavailable",
                notes=(
                    "No reliable aggregated population attribute on this zone; "
                    "component excluded (values are never invented)."
                ),
            )
        )
    else:
        inputs.append(
            ComponentInput(
                key="population_exposure",
                raw_value=float(pop),
                status="synthetic" if features.get("population_is_synthetic") else "available",
                is_synthetic=bool(features.get("population_is_synthetic")),
                source_refs=list(features.get("population_sources") or []),
                notes=features.get("population_notes"),
            )
        )

    # Road disruption
    road_raw = features.get("road_disruption_index")
    inputs.append(
        ComponentInput(
            key="road_disruption_risk",
            raw_value=float(road_raw) if road_raw is not None else None,
            status=features.get("road_status", "unavailable"),
            is_synthetic=bool(features.get("road_is_synthetic")),
            source_refs=list(features.get("road_sources") or []),
            notes=features.get("road_notes"),
        )
    )

    # Healthcare travel
    travel = features.get("nearest_healthcare_km")
    inputs.append(
        ComponentInput(
            key="healthcare_travel_burden",
            raw_value=float(travel) if travel is not None else None,
            status=features.get("healthcare_status", "unavailable"),
            is_synthetic=bool(features.get("healthcare_is_synthetic")),
            source_refs=list(features.get("healthcare_sources") or []),
            notes=features.get("healthcare_notes"),
        )
    )

    # Infrastructure availability
    fac = features.get("facility_count")
    inputs.append(
        ComponentInput(
            key="infrastructure_availability",
            raw_value=float(fac) if fac is not None else None,
            status=features.get("facility_status", "unavailable"),
            is_synthetic=bool(features.get("facility_is_synthetic")),
            source_refs=list(features.get("facility_sources") or []),
            notes=features.get("facility_notes"),
        )
    )

    return combine_components(
        inputs,
        cfg,
        zone_label=zone_label,
        extra_inputs={
            k: v
            for k, v in features.items()
            if k
            not in {
                "flood_notes",
                "population_notes",
                "road_notes",
                "healthcare_notes",
                "facility_notes",
            }
        },
    )


def _unavailable_score(
    defn: ComponentDefinition, inp: Optional[ComponentInput]
) -> ComponentScore:
    return ComponentScore(
        key=defn.key,
        label=defn.label,
        status="unavailable",
        raw_value=None,
        normalized_score=None,
        weight_configured=defn.weight,
        weight_effective=0.0,
        direction=defn.direction,
        is_synthetic=False,
        contribution=None,
        reason=(inp.notes if inp and inp.notes else f"{defn.label} unavailable"),
        source_refs=list(inp.source_refs) if inp else [],
        limitations=defn.limitations,
    )


def _component_reason(
    defn: ComponentDefinition,
    raw: float,
    norm: float,
    effective_weight: float,
    is_synthetic: bool,
) -> str:
    synth = " [synthetic demonstration value]" if is_synthetic else ""
    return (
        f"{defn.label}: raw={raw:g} {defn.unit} → normalized vulnerability "
        f"{norm:.1f}/100 (effective weight {effective_weight:.2%}){synth}."
    )


def _narrative(
    zone_label: str,
    overall: float,
    category: str,
    components: list[ComponentScore],
    confidence: float,
) -> str:
    drivers = sorted(
        [c for c in components if c.contribution is not None],
        key=lambda c: c.contribution or 0,
        reverse=True,
    )
    top = drivers[:3]
    parts = [
        f"{zone_label} received an overall vulnerability score of {overall:.1f}/100 "
        f"({category}) under scoring model {components[0].key and ''}."
        if False
        else (
            f"{zone_label} received an overall vulnerability score of {overall:.1f}/100 "
            f"classified as '{category}'. Confidence indicator: {confidence:.0%} "
            "(reflects data coverage and synthetic share — not predictive accuracy)."
        )
    ]
    if top:
        driver_txt = "; ".join(
            f"{c.label} contributed {c.contribution:.1f} points" for c in top
        )
        parts.append(f"Primary drivers: {driver_txt}.")
    missing = [c.label for c in components if c.status == "unavailable"]
    if missing:
        parts.append(
            "Unavailable components (excluded, not zero-filled): "
            + ", ".join(missing)
            + "."
        )
    return " ".join(parts)

"""
Configurable vulnerability scoring methodology (Module 2).

This is an analytical demonstration model for Nagpur flood + emergency healthcare
accessibility. It is NOT a validated predictive model and must not be presented
as official risk ratings.

Weights can be changed via SCORING_WEIGHTS_JSON env (JSON object of component→weight)
without rewriting the engine.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Optional

SCORING_VERSION = "v1.0-nagpur-flood-health"

ComponentStatus = Literal["available", "unavailable", "synthetic"]
Direction = Literal["higher_worse", "higher_better"]


@dataclass(frozen=True)
class ComponentDefinition:
    key: str
    label: str
    description: str
    direction: Direction
    weight: float
    # Fixed scale for linear normalization to 0–100 (vulnerability contribution)
    raw_min: float
    raw_max: float
    unit: str
    limitations: str


@dataclass(frozen=True)
class CategoryThreshold:
    category: str
    min_inclusive: float
    max_exclusive: float
    description: str


@dataclass(frozen=True)
class ScoringConfig:
    version: str = SCORING_VERSION
    study_area: str = "Nagpur, Maharashtra, India"
    disclaimer: str = (
        "Scores are transparent analytical composites for software demonstration "
        "and prioritisation research. They are not validated flood forecasts, "
        "official risk maps, or measured hospital travel times."
    )
    components: tuple[ComponentDefinition, ...] = field(default_factory=tuple)
    categories: tuple[CategoryThreshold, ...] = field(default_factory=tuple)

    def weight_map(self) -> dict[str, float]:
        return {c.key: c.weight for c in self.components}

    def component(self, key: str) -> ComponentDefinition:
        for c in self.components:
            if c.key == key:
                return c
        raise KeyError(key)

    def with_weights(self, overrides: dict[str, float]) -> "ScoringConfig":
        """Return a copy with updated weights (must be > 0 for provided keys)."""
        new_components = []
        for c in self.components:
            if c.key in overrides:
                w = float(overrides[c.key])
                if w < 0:
                    raise ValueError(f"Weight for {c.key} must be >= 0")
                new_components.append(replace(c, weight=w))
            else:
                new_components.append(c)
        total = sum(c.weight for c in new_components)
        if total <= 0:
            raise ValueError("At least one component weight must be > 0")
        return replace(self, components=tuple(new_components))

    def documentation(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "study_area": self.study_area,
            "disclaimer": self.disclaimer,
            "normalization": (
                "Each available component is linearly mapped from its documented "
                "raw_min/raw_max to 0–100. Direction higher_better is inverted so "
                "all contributions increase overall vulnerability."
            ),
            "missing_data_policy": (
                "Unavailable components are excluded from the weighted sum; "
                "remaining positive weights are renormalized to sum to 1.0. "
                "Values are never silently filled with zeros."
            ),
            "components": [
                {
                    "key": c.key,
                    "label": c.label,
                    "description": c.description,
                    "direction": c.direction,
                    "weight": c.weight,
                    "raw_min": c.raw_min,
                    "raw_max": c.raw_max,
                    "unit": c.unit,
                    "limitations": c.limitations,
                }
                for c in self.components
            ],
            "categories": [
                {
                    "category": t.category,
                    "min_inclusive": t.min_inclusive,
                    "max_exclusive": t.max_exclusive,
                    "description": t.description,
                }
                for t in self.categories
            ],
        }


def default_scoring_config() -> ScoringConfig:
    components = (
        ComponentDefinition(
            key="flood_hazard_exposure",
            label="Flood hazard exposure",
            description=(
                "Severity-weighted flood/waterlogging observations intersecting "
                "the zone boundary (PostGIS)."
            ),
            direction="higher_worse",
            weight=0.30,
            raw_min=0.0,
            raw_max=10.0,
            unit="severity-weighted observation score",
            limitations=(
                "Depends on imported hazard points; sparse OSM/synthetic markers "
                "are not official flood statistics."
            ),
        ),
        ComponentDefinition(
            key="population_exposure",
            label="Population / community exposure",
            description=(
                "Relative community exposure when reliable aggregated population "
                "data exists in zone properties."
            ),
            direction="higher_worse",
            weight=0.15,
            raw_min=0.0,
            raw_max=100000.0,
            unit="population (if present in properties)",
            limitations=(
                "Official census figures are not invented. Without authentic "
                "population attributes the component is marked unavailable."
            ),
        ),
        ComponentDefinition(
            key="road_disruption_risk",
            label="Road accessibility / disruption risk",
            description=(
                "Proxy for potential road disruption: flood markers near roads "
                "and scarcity of mapped road nodes inside the zone."
            ),
            direction="higher_worse",
            weight=0.20,
            raw_min=0.0,
            raw_max=10.0,
            unit="disruption proxy index",
            limitations=(
                "Road geometries from OSM may be incomplete; disruption is "
                "hypothesized from co-location, not traffic models."
            ),
        ),
        ComponentDefinition(
            key="healthcare_travel_burden",
            label="Emergency healthcare travel burden",
            description=(
                "Great-circle distance (km) from zone centroid to nearest "
                "hospital/clinic/emergency facility."
            ),
            direction="higher_worse",
            weight=0.25,
            raw_min=0.0,
            raw_max=15.0,
            unit="kilometres (approximate, not measured travel time)",
            limitations=(
                "Distance is geometric, not network travel time. Does not claim "
                "ambulance ETA accuracy."
            ),
        ),
        ComponentDefinition(
            key="infrastructure_availability",
            label="Relevant infrastructure availability",
            description=(
                "Count of emergency-relevant facilities (hospital, clinic, "
                "emergency_facility) intersecting or within the zone."
            ),
            direction="higher_better",
            weight=0.10,
            raw_min=0.0,
            raw_max=5.0,
            unit="facility count",
            limitations=(
                "Presence ≠ capacity, staffing, or flood-resilience of facilities."
            ),
        ),
    )
    categories = (
        CategoryThreshold(
            "low", 0.0, 25.0, "Lower relative composite vulnerability in this model"
        ),
        CategoryThreshold(
            "moderate", 25.0, 50.0, "Elevated factors; review component drivers"
        ),
        CategoryThreshold(
            "high", 50.0, 75.0, "Multiple adverse factors contribute strongly"
        ),
        CategoryThreshold(
            "critical",
            75.0,
            100.01,
            "Highest relative composite in this model configuration",
        ),
    )
    return ScoringConfig(components=components, categories=categories)


def load_scoring_config(
    weight_overrides: Optional[dict[str, float]] = None,
) -> ScoringConfig:
    """Load default config, apply SCORING_WEIGHTS_JSON env, then call overrides."""
    cfg = default_scoring_config()
    env_raw = os.environ.get("SCORING_WEIGHTS_JSON", "").strip()
    if env_raw:
        try:
            env_weights = json.loads(env_raw)
            if not isinstance(env_weights, dict):
                raise ValueError("SCORING_WEIGHTS_JSON must be a JSON object")
            cfg = cfg.with_weights({str(k): float(v) for k, v in env_weights.items()})
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid SCORING_WEIGHTS_JSON: {exc}") from exc
    if weight_overrides:
        cfg = cfg.with_weights(weight_overrides)
    return cfg

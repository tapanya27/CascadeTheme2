"""Unit tests for vulnerability scoring (pure functions)."""

from __future__ import annotations

import pytest

from app.scoring.config import default_scoring_config, load_scoring_config
from app.scoring.engine import (
    ComponentInput,
    categorize,
    combine_components,
    normalize_linear,
    score_zone_features,
)


def test_normalize_linear_higher_worse():
    assert normalize_linear(0, 0, 10) == 0.0
    assert normalize_linear(10, 0, 10) == 100.0
    assert normalize_linear(5, 0, 10) == 50.0


def test_normalize_linear_higher_better_inverted():
    assert normalize_linear(0, 0, 5, invert=True) == 100.0
    assert normalize_linear(5, 0, 5, invert=True) == 0.0


def test_normalize_clamps():
    assert normalize_linear(-5, 0, 10) == 0.0
    assert normalize_linear(99, 0, 10) == 100.0


def test_categorize_thresholds():
    assert categorize(0) == "low"
    assert categorize(24.9) == "low"
    assert categorize(25) == "moderate"
    assert categorize(50) == "high"
    assert categorize(75) == "critical"
    assert categorize(100) == "critical"


def test_missing_components_excluded_not_zero_filled():
    cfg = default_scoring_config()
    result = combine_components(
        [
            ComponentInput(
                key="flood_hazard_exposure",
                raw_value=5.0,
                status="available",
                source_refs=["test"],
            ),
            # others unavailable by omission
        ],
        cfg,
        zone_label="Test Zone",
    )
    assert result.overall_score is not None
    unavailable = [c for c in result.components if c.status == "unavailable"]
    assert len(unavailable) >= 3
    assert all(c.contribution is None for c in unavailable)
    assert result.data_quality["weights_renormalized"] is True
    assert "excluded" in " ".join(result.reasons).lower() or "unavailable" in " ".join(
        result.reasons
    ).lower()


def test_all_unavailable_withholds_score():
    result = combine_components([], default_scoring_config(), zone_label="Empty")
    assert result.overall_score is None
    assert result.category is None
    assert result.confidence == 0.0


def test_weight_overrides_change_score():
    features = {
        "zone_name": "Z",
        "flood_severity_score": 8.0,
        "flood_status": "available",
        "road_disruption_index": 2.0,
        "road_status": "available",
        "nearest_healthcare_km": 1.0,
        "healthcare_status": "available",
        "facility_count": 2,
        "facility_status": "available",
    }
    base = score_zone_features(features, default_scoring_config())
    flood_heavy = score_zone_features(
        features,
        load_scoring_config(
            {
                "flood_hazard_exposure": 0.9,
                "population_exposure": 0.0,
                "road_disruption_risk": 0.05,
                "healthcare_travel_burden": 0.05,
                "infrastructure_availability": 0.0,
            }
        ),
    )
    assert base.overall_score is not None
    assert flood_heavy.overall_score is not None
    # Heavier flood weight with high flood raw should push score up vs balanced
    assert flood_heavy.overall_score >= base.overall_score - 1e-6


def test_repeatability_identical_inputs():
    features = {
        "zone_name": "Repeat",
        "flood_severity_score": 3.0,
        "flood_status": "available",
        "road_disruption_index": 4.0,
        "road_status": "available",
        "nearest_healthcare_km": 2.5,
        "healthcare_status": "available",
        "facility_count": 1,
        "facility_status": "available",
    }
    a = score_zone_features(features)
    b = score_zone_features(features)
    assert a.overall_score == b.overall_score
    assert a.category == b.category
    assert a.weights_used == b.weights_used


def test_explanations_match_components():
    result = score_zone_features(
        {
            "zone_name": "Explain",
            "flood_severity_score": 4.0,
            "flood_status": "available",
            "road_disruption_index": 3.0,
            "road_status": "available",
            "nearest_healthcare_km": 6.0,
            "healthcare_status": "available",
            "facility_count": 0,
            "facility_status": "available",
        }
    )
    assert result.narrative
    for c in result.components:
        if c.status != "unavailable":
            assert c.key in " ".join(result.reasons) or c.label.split()[0] in " ".join(
                result.reasons
            )
            assert c.reason


def test_synthetic_flag_reduces_confidence():
    authentic = score_zone_features(
        {
            "zone_name": "A",
            "flood_severity_score": 4.0,
            "flood_status": "available",
            "flood_is_synthetic": False,
            "road_disruption_index": 3.0,
            "road_status": "available",
            "nearest_healthcare_km": 2.0,
            "healthcare_status": "available",
            "facility_count": 1,
            "facility_status": "available",
        }
    )
    synthetic = score_zone_features(
        {
            "zone_name": "S",
            "flood_severity_score": 4.0,
            "flood_status": "synthetic",
            "flood_is_synthetic": True,
            "road_disruption_index": 3.0,
            "road_status": "synthetic",
            "road_is_synthetic": True,
            "nearest_healthcare_km": 2.0,
            "healthcare_status": "synthetic",
            "healthcare_is_synthetic": True,
            "facility_count": 1,
            "facility_status": "synthetic",
            "facility_is_synthetic": True,
        }
    )
    assert authentic.confidence > synthetic.confidence
    assert any(c.is_synthetic for c in synthetic.components if c.status != "unavailable")


def test_invalid_weight_rejected():
    with pytest.raises(ValueError):
        load_scoring_config({"flood_hazard_exposure": -1})

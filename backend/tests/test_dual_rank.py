"""Dual ranking and rank uplift unit tests (no DB)."""

from app.scoring.dual_rank import compute_dual_rankings, score_hazard_only
from app.scoring.engine import score_zone_features


def _features(**overrides):
    base = {
        "zone_id": "00000000-0000-0000-0000-000000000001",
        "zone_code": "Z1",
        "zone_name": "Zone 1",
        "flood_severity_score": 6.0,
        "flood_status": "available",
        "flood_is_synthetic": False,
        "flood_sources": ["test"],
        "population": 10000,
        "population_is_synthetic": False,
        "road_disruption_index": 4.0,
        "road_status": "available",
        "nearest_healthcare_km": 8.0,
        "healthcare_status": "available",
        "facility_count": 1,
        "infrastructure_status": "available",
    }
    base.update(overrides)
    return base


def test_hazard_only_uses_flood_component():
    f = _features()
    h = score_hazard_only(f)
    m = score_zone_features(f)
    assert h.overall_score is not None
    assert m.overall_score is not None
    # Hazard-only should equal normalized flood contribution alone
    flood_comp = next(c for c in h.components if c.key == "flood_hazard_exposure")
    assert flood_comp.normalized_score == h.overall_score


def test_rank_uplift_positive_when_multifactor_raises_priority():
    # Zone A: high flood, good healthcare → hazard rank high, multifactor may drop
    # Zone B: moderate flood, terrible healthcare/population → multifactor may rise
    zones = [
        {
            "zone_id": "a",
            "zone_code": "A",
            "hazard_score": 90.0,
            "multifactor_score": 40.0,
        },
        {
            "zone_id": "b",
            "zone_code": "B",
            "hazard_score": 50.0,
            "multifactor_score": 80.0,
        },
    ]
    ranked = compute_dual_rankings(zones)
    by_id = {r["zone_id"]: r for r in ranked}
    assert by_id["a"]["hazard_only_rank"] == 1
    assert by_id["b"]["hazard_only_rank"] == 2
    assert by_id["b"]["multifactor_rank"] == 1
    assert by_id["b"]["rank_uplift"] == 1  # moved up
    assert by_id["a"]["rank_uplift"] == -1  # moved down

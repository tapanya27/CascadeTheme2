"""Cascade response enrichment — names, city scope, scenario distinctions."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.cascade_simulator import CascadeSimulator, SCENARIO_TYPES


def test_scenario_types_include_bus_and_power():
    assert "bus_service_disruption" in SCENARIO_TYPES
    assert "power_failure" in SCENARIO_TYPES
    assert SCENARIO_TYPES >= {
        "road_closure",
        "hospital_outage",
        "power_failure",
        "bus_service_disruption",
        "multi_failure",
        "weather_source_loss",
        "infrastructure_source_loss",
    }


def test_resolve_infra_empty():
    db = MagicMock()
    sim = CascadeSimulator.__new__(CascadeSimulator)
    sim.db = db
    assert sim._resolve_infra([], city_id="nagpur") == []


def test_weather_notes_do_not_claim_flood(monkeypatch):
    """Weather source loss must mark hazard unavailable without inventing a flood."""
    from app.services import cascade_simulator as mod

    class FakeDual(dict):
        pass

    def fake_extract(db, zone_ids=None, city_id=None):
        return [
            {
                "zone_id": "11111111-1111-1111-1111-111111111111",
                "zone_code": "NAG-001",
                "zone_name": "Sitabuldi",
                "flood_severity_score": 4.0,
                "facility_count": 2,
                "nearest_healthcare_km": 3.0,
                "road_disruption_index": 2.0,
            }
        ]

    def fake_dual(features, weight_overrides=None):
        return {
            "zone_id": features["zone_id"],
            "zone_code": features["zone_code"],
            "zone_name": features["zone_name"],
            "hazard_score": 10.0 if features.get("flood_severity_score") else None,
            "multifactor_score": 40.0,
            "multifactor_category": "moderate",
            "confidence": 0.5 if features.get("flood_severity_score") is None else 0.8,
            "limitations": [],
        }

    def fake_rank(rows):
        out = []
        for i, r in enumerate(rows):
            out.append(
                {
                    **r,
                    "multifactor_rank": i + 1,
                    "hazard_only_rank": i + 1,
                    "rank_uplift": 0,
                }
            )
        return out

    monkeypatch.setattr(mod, "extract_all_zone_features", fake_extract)
    monkeypatch.setattr(mod, "dual_score_zone", fake_dual)
    monkeypatch.setattr(mod, "compute_dual_rankings", fake_rank)

    db = MagicMock()
    sim = CascadeSimulator(db)
    monkeypatch.setattr(sim, "build_extended_graph", lambda city_id=None: __import__("networkx").DiGraph())
    monkeypatch.setattr(sim, "_resolve_infra", lambda ids, city_id=None: [])

    result = sim.simulate(scenario_type="weather_source_loss", city_id="nagpur")
    assert result["city_id"] == "nagpur"
    assert "hazard" in result["lost_source_kinds"]
    impact = result["zone_impacts"][0]
    assert impact["zone_name"] == "Sitabuldi"
    assert impact["display_name"] == "Sitabuldi"
    assert "hazard_data_unavailable" in impact["service_effects"]
    assert impact.get("flood_notes") and "does not mean a flood" in impact["flood_notes"].lower()


def test_power_failure_sets_illustrative(monkeypatch):
    from app.services import cascade_simulator as mod
    import networkx as nx

    def fake_extract(db, zone_ids=None, city_id=None):
        return [
            {
                "zone_id": "22222222-2222-2222-2222-222222222222",
                "zone_code": "NAG-002",
                "zone_name": "Civil Lines",
                "facility_count": 3,
                "nearest_healthcare_km": 2.0,
            }
        ]

    def fake_dual(features, weight_overrides=None):
        return {
            "zone_id": features["zone_id"],
            "zone_code": features["zone_code"],
            "zone_name": features["zone_name"],
            "hazard_score": None,
            "multifactor_score": 35.0,
            "multifactor_category": "moderate",
            "confidence": 0.6,
            "limitations": [],
        }

    def fake_rank(rows):
        return [
            {
                **r,
                "multifactor_rank": 1,
                "hazard_only_rank": 1,
                "rank_uplift": 0,
            }
            for r in rows
        ]

    monkeypatch.setattr(mod, "extract_all_zone_features", fake_extract)
    monkeypatch.setattr(mod, "dual_score_zone", fake_dual)
    monkeypatch.setattr(mod, "compute_dual_rankings", fake_rank)

    sim = CascadeSimulator(MagicMock())
    monkeypatch.setattr(sim, "build_extended_graph", lambda city_id=None: nx.DiGraph())
    monkeypatch.setattr(sim, "_resolve_infra", lambda ids, city_id=None: [])

    result = sim.simulate(scenario_type="power_failure", city_id="nagpur")
    # Without power_asset rows in the mocked DB sample, expect illustrative gap note
    # (live DB with seeded power assets will attach a selected_power_asset instead).
    assert result["scenario_type"] == "power_failure"
    assert result.get("selected_route") is None
    assert "selected_power_asset" in result

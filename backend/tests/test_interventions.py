"""Intervention scenario and sensitivity tests."""

from __future__ import annotations

import pytest

from app.models.intervention import InterventionType
from app.services.intervention_service import (
    InterventionEvaluationError,
    apply_intervention,
)


def test_place_resource_requires_coords():
    with pytest.raises(InterventionEvaluationError):
        apply_intervention(
            {"nearest_healthcare_km": 5.0, "facility_count": 0},
            InterventionType.place_temporary_resource,
            {},
            centroid=(79.08, 21.14),
        )


def test_place_resource_improves_distance():
    feat, assumptions, limitations = apply_intervention(
        {
            "nearest_healthcare_km": 10.0,
            "facility_count": 0,
            "healthcare_status": "available",
        },
        InterventionType.place_temporary_resource,
        {"lon": 79.09, "lat": 21.15},
        centroid=(79.08, 21.14),
    )
    assert feat["nearest_healthcare_km"] < 10.0
    assert feat["facility_count"] == 1
    assert assumptions
    assert any("simulation" in x.lower() or "heuristic" in x.lower() for x in limitations)


def test_route_requires_assumption():
    with pytest.raises(InterventionEvaluationError):
        apply_intervention(
            {"road_disruption_index": 5.0},
            InterventionType.alternative_emergency_route,
            {},
            centroid=(79.08, 21.14),
        )


def test_route_relative_reduction():
    feat, _, _ = apply_intervention(
        {"road_disruption_index": 8.0, "road_status": "available"},
        InterventionType.alternative_emergency_route,
        {"assumed_relative_reduction": 0.5},
        centroid=(79.08, 21.14),
    )
    assert feat["road_disruption_index"] == 4.0


def test_accessibility_rejects_invented_defaults():
    with pytest.raises(InterventionEvaluationError):
        apply_intervention(
            {},
            InterventionType.accessibility_improvement,
            {},
            centroid=(79.08, 21.14),
        )


def test_intervention_api_compare_and_list(client, database_available, db_session):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")

    from app.services.synthetic_data import seed_synthetic_dataset

    seed_synthetic_dataset(db_session, city_id="nagpur")
    db_session.commit()
    client.post("/api/assessments/run", params={"city_id": "nagpur"}, json={})

    zones = client.get(
        "/api/zones", params={"city_id": "nagpur"}
    ).json()["items"]
    zid = zones[0]["id"]

    bad = client.post(
        "/api/interventions/compare",
        params={"city_id": "nagpur"},
        json={
            "zone_id": zid,
            "intervention_type": "place_temporary_resource",
            "name": "Missing coords",
            "params": {},
        },
    )
    assert bad.status_code == 422

    ok = client.post(
        "/api/interventions/compare",
        params={"city_id": "nagpur"},
        json={
            "zone_id": zid,
            "intervention_type": "place_temporary_resource",
            "name": "Temp hub near zone",
            "params": {"lon": 79.09, "lat": 21.15},
        },
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert "SIMULATION" in body["simulation_label"]
    assert body["results"]["kind"] == "single"
    assert body["baseline"]["score"] is not None

    listing = client.get("/api/interventions", params={"city_id": "nagpur"})
    assert listing.status_code == 200
    assert listing.json()["total"] >= 1
    assert listing.json()["catalog"]

    detail = client.get(
        f"/api/interventions/{body['id']}", params={"city_id": "nagpur"}
    )
    assert detail.status_code == 200
    assert detail.json()["id"] == body["id"]


def test_sensitivity_endpoint(client, database_available, db_session):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    from app.services.synthetic_data import seed_synthetic_dataset

    seed_synthetic_dataset(db_session, city_id="nagpur")
    db_session.commit()

    resp = client.post(
        "/api/assessments/sensitivity",
        params={"city_id": "nagpur"},
        json={"perturbation": 0.2},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "heuristic" in body["method"]
    assert "not" in body["disclaimer"].lower() or "Not" in body["disclaimer"]
    assert "baseline_ranking" in body
    assert "variants" in body


def test_upload_rejects_oversize(monkeypatch):
    import asyncio
    from io import BytesIO

    from fastapi import HTTPException, UploadFile

    from app.config import get_settings
    from app.security import read_upload_limited

    get_settings.cache_clear()
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://critical1:critical1_dev@localhost:5433/critical1",
    )
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "10")
    get_settings.cache_clear()

    upload = UploadFile(filename="t.csv", file=BytesIO(b"x" * 50))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(read_upload_limited(upload))
    assert exc.value.status_code == 413
    get_settings.cache_clear()

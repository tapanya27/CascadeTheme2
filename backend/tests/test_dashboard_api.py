"""Dashboard overview and map layer API tests."""

from __future__ import annotations

import pytest


def test_overview_and_map_layers(client, database_available, db_session):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")

    from app.services.synthetic_data import seed_synthetic_dataset

    seed_synthetic_dataset(db_session, city_id="nagpur")
    db_session.commit()
    client.post("/api/assessments/run", params={"city_id": "nagpur"}, json={})

    overview = client.get(
        "/api/dashboard/overview", params={"city_id": "nagpur"}
    )
    assert overview.status_code == 200
    body = overview.json()
    assert body["city_id"] == "nagpur"
    assert body["total_zones"] >= 1
    assert "category_counts" in body
    assert "freshness" in body
    assert "disclaimer" in body
    assert body["zones_assessed"] >= 1

    layers = client.get("/api/map/layers", params={"city_id": "nagpur"})
    assert layers.status_code == 200
    payload = layers.json()
    assert payload["city_id"] == "nagpur"
    assert payload["zones"]["type"] == "FeatureCollection"
    assert len(payload["zones"]["features"]) >= 1
    feat = payload["zones"]["features"][0]
    assert feat["geometry"]
    assert "properties" in feat
    assert "is_synthetic" in feat["properties"]
    assert "category" in feat["properties"] or feat["properties"].get(
        "overall_score"
    ) is not None

    zid = feat["properties"]["id"]
    ctx = client.get(
        f"/api/zones/{zid}/context", params={"city_id": "nagpur"}
    )
    assert ctx.status_code == 200
    ctx_body = ctx.json()
    assert ctx_body["zone_id"] == zid
    assert ctx_body["city_id"] == "nagpur"
    assert "hazards" in ctx_body
    assert "infrastructure" in ctx_body


def test_zone_context_not_found(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    resp = client.get(
        "/api/zones/00000000-0000-0000-0000-000000000099/context",
        params={"city_id": "nagpur"},
    )
    assert resp.status_code == 404

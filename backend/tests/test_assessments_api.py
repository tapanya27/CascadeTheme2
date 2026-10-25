"""PostgreSQL-backed assessment and dependency API tests."""

from __future__ import annotations

import pytest


def test_run_and_latest_assessments(client, database_available, db_session):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")

    from app.services.synthetic_data import seed_synthetic_dataset

    seed_synthetic_dataset(db_session, city_id="nagpur")
    db_session.commit()

    run = client.post(
        "/api/assessments/run", params={"city_id": "nagpur"}, json={}
    )
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["assessed"] >= 1
    assert body["run_id"]
    assert "methodology" in body
    first = body["assessments"][0]
    assert "components" in first
    assert "explanation" in first
    assert "data_quality" in first
    assert "confidence" in first

    latest = client.get(
        "/api/assessments/latest", params={"city_id": "nagpur"}
    )
    assert latest.status_code == 200
    latest_body = latest.json()
    assert latest_body["total"] == body["assessed"]
    assert latest_body["run_id"] == body["run_id"]


def test_zone_explanation_endpoint(client, database_available, db_session):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")

    from app.services.synthetic_data import seed_synthetic_dataset

    seed_synthetic_dataset(db_session, city_id="nagpur")
    db_session.commit()
    client.post("/api/assessments/run", params={"city_id": "nagpur"}, json={})

    zones = client.get("/api/zones", params={"city_id": "nagpur"}).json()
    assert zones["total"] >= 1
    zid = zones["items"][0]["id"]

    detail = client.get(f"/api/zones/{zid}", params={"city_id": "nagpur"})
    assert detail.status_code == 200

    expl = client.get(
        f"/api/zones/{zid}/explanation", params={"city_id": "nagpur"}
    )
    assert expl.status_code == 200
    payload = expl.json()
    assert payload["assessment"] is not None
    assert payload["assessment"]["explanation"]
    assert len(payload["assessment"]["components"]) >= 1


def test_dependency_graph_structure(client, database_available, db_session):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")

    resp = client.get(
        "/api/dependency-graph", params={"city_id": "nagpur"}
    )
    assert resp.status_code == 200
    graph = resp.json()
    assert len(graph["nodes"]) >= 4
    assert len(graph["edges"]) >= 4
    assert "is_dag" in graph
    kinds = {e["evidence_kind"] for e in graph["edges"]}
    assert kinds <= {"observed", "assumed", "hypothesized"}
    assert kinds & {"assumed", "hypothesized"}
    for e in graph["edges"]:
        assert "provenance" in e
        assert e["source"] and e["target"]


def test_assessment_run_invalid_weights(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    resp = client.post(
        "/api/assessments/run",
        params={"city_id": "nagpur"},
        json={"weight_overrides": {"flood_hazard_exposure": -5}},
    )
    assert resp.status_code == 400


def test_zone_not_found_explanation(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    resp = client.get(
        "/api/zones/00000000-0000-0000-0000-000000000099/explanation",
        params={"city_id": "nagpur"},
    )
    assert resp.status_code == 404

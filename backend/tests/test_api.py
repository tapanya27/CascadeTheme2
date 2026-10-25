"""API endpoint tests."""

from __future__ import annotations

import pytest


def test_health_endpoint_shape(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert "database" in body
    assert "postgis" in body
    assert body["database"] in {"connected", "unavailable"}
    # When DB is down, status must be degraded — never silently pretend OK with SQLite
    if body["database"] != "connected" or not body["postgis"]:
        assert body["status"] == "degraded"
        assert body.get("error")


def test_metadata_endpoint(client):
    resp = client.get("/api/metadata")
    assert resp.status_code == 200
    body = resp.json()
    assert "Nagpur" in body["study_area"]
    assert body["database_required"].startswith("PostgreSQL")
    assert any("health" in e for e in body["endpoints"])


def test_zones_requires_db(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    resp = client.get("/api/zones", params={"city_id": "nagpur"})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body


def test_data_sources_endpoint(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    resp = client.get("/api/data/sources", params={"city_id": "nagpur"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_validate_bad_file_type(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    resp = client.post(
        "/api/data/validate",
        files={"file": ("x.bin", b"abc", "application/octet-stream")},
        data={"record_type": "infrastructure"},
    )
    assert resp.status_code == 400


def test_validate_invalid_csv_coordinates(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    csv = b"name,infrastructure_type,lon,lat\nX,hospital,999,21\n"
    resp = client.post(
        "/api/data/validate",
        files={"file": ("t.csv", csv, "text/csv")},
        data={"record_type": "infrastructure"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["invalid_rows"] >= 1


def test_import_rejects_invalid_payload(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    csv = b"name,infrastructure_type,lon,lat\nX,hospital,999,21\n"
    resp = client.post(
        "/api/data/import",
        params={"city_id": "nagpur"},
        files={"file": ("t.csv", csv, "text/csv")},
        data={"record_type": "infrastructure", "commit": "true"},
    )
    assert resp.status_code == 422


def test_export_includes_provenance_note(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    resp = client.get("/api/data/export", params={"city_id": "nagpur"})
    assert resp.status_code == 200
    body = resp.json()
    assert "synthetic" in body["note"].lower()
    assert "data_sources" in body


def test_zone_not_found(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    resp = client.get(
        "/api/zones/00000000-0000-0000-0000-000000000099",
        params={"city_id": "nagpur"},
    )
    assert resp.status_code == 404

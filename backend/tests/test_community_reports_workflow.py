"""End-to-end community report → map workflow tests."""

from __future__ import annotations

from uuid import UUID

import pytest

from app.models.community_report import CommunityReport
from app.nlp.reports import primary_category, redact_pii


def test_primary_category_helpers():
    assert primary_category(["flooding"], disaster_related=True) == "flooding"
    assert primary_category([], disaster_related=False) == "not_disaster_related"
    assert primary_category([], disaster_related=True) == "unclassified"


def test_submit_persists_redacted_only(client, database_available, db_session):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")

    raw = "Flooding near clinic — call 555-987-6543 or help@example.com"
    resp = client.post(
        "/api/reports/submit",
        params={"city_id": "nagpur"},
        json={"text": raw, "lat": 21.15, "lon": 79.09},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verification_status"] == "unverified"
    assert body["city_id"] == "nagpur"
    assert body["has_map_marker"] is True
    assert body["stored_text_redacted_only"] is True
    assert "555-987-6543" not in body["report"]["text_redacted"]
    assert "help@example.com" not in body["report"]["text_redacted"]
    assert "PHONE_REDACTED" in body["report"]["text_redacted"] or "EMAIL_REDACTED" in body[
        "report"
    ]["text_redacted"]
    assert body["category"]

    row = db_session.get(CommunityReport, UUID(body["id"]))
    assert row is not None
    db_session.refresh(row)
    assert row.city_id == "nagpur"
    assert row.verification_status == "unverified"
    assert "555-987-6543" not in row.text_redacted
    assert "help@example.com" not in row.text_redacted
    assert raw not in row.text_redacted
    assert row.location_precision == "coordinates"
    assert row.location.get("lon") == 79.09
    assert row.location.get("lat") == 21.15


def test_submit_without_coords_no_map_marker(client, database_available, db_session):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")

    resp = client.post(
        "/api/reports/submit",
        params={"city_id": "nagpur"},
        json={"text": "Blocked roads after heavy rain near market"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_map_marker"] is False
    assert body["location_precision"] in {"city", "unknown"}
    assert "lon" not in (body["report"]["location"] or {})
    assert "lat" not in (body["report"]["location"] or {})

    layers = client.get("/api/map/layers", params={"city_id": "nagpur"}).json()
    report_ids = {
        str(f["properties"]["id"])
        for f in layers.get("community_reports", {}).get("features", [])
    }
    assert body["id"] not in report_ids

    listing = client.get("/api/reports", params={"city_id": "nagpur"}).json()
    ids = {r["id"] for r in listing["items"]}
    assert body["id"] in ids


def test_coords_must_be_paired(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    resp = client.post(
        "/api/reports/submit",
        params={"city_id": "nagpur"},
        json={"text": "Flood water rising", "lat": 21.1},
    )
    assert resp.status_code == 422


def test_coords_out_of_range(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    resp = client.post(
        "/api/reports/submit",
        params={"city_id": "nagpur"},
        json={"text": "Flood water rising", "lat": 120.0, "lon": 79.0},
    )
    assert resp.status_code == 422


def test_city_isolation_reports(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")

    nag = client.post(
        "/api/reports/submit",
        params={"city_id": "nagpur"},
        json={"text": "Medical needs at temporary shelter", "lat": 21.14, "lon": 79.08},
    )
    assert nag.status_code == 200
    nag_id = nag.json()["id"]

    kat = client.get("/api/reports", params={"city_id": "kathmandu"})
    assert kat.status_code == 200
    assert all(r["id"] != nag_id for r in kat.json()["items"])
    assert kat.json()["city_id"] == "kathmandu"

    kat_layers = client.get(
        "/api/map/layers", params={"city_id": "kathmandu"}
    ).json()
    kat_ids = {
        str(f["properties"]["id"])
        for f in kat_layers.get("community_reports", {}).get("features", [])
    }
    assert nag_id not in kat_ids

    # Cross-city review blocked
    review = client.post(
        f"/api/reports/{nag_id}/review",
        params={"city_id": "kathmandu"},
        json={"reviewed": True},
    )
    assert review.status_code == 404


def test_located_report_appears_on_map_layer(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")

    resp = client.post(
        "/api/reports/submit",
        params={"city_id": "nagpur"},
        json={
            "text": "Flooding reported on main road",
            "lat": 21.146,
            "lon": 79.088,
        },
    )
    assert resp.status_code == 200
    rid = resp.json()["id"]
    assert resp.json()["has_map_marker"] is True

    layers = client.get("/api/map/layers", params={"city_id": "nagpur"}).json()
    feats = layers["community_reports"]["features"]
    match = [f for f in feats if str(f["properties"]["id"]) == rid]
    assert len(match) == 1
    props = match[0]["properties"]
    assert props["verification_status"] == "unverified"
    assert props["category"]
    assert props["created_at"]
    assert match[0]["geometry"]["type"] == "Point"
    assert match[0]["geometry"]["coordinates"] == [79.088, 21.146]


def test_uncertain_classification_flags_review(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")

    # Ambiguous short text — keyword/model should still flag review for low confidence
    resp = client.post(
        "/api/reports/submit",
        params={"city_id": "nagpur"},
        json={"text": "Something odd happening downtown today maybe"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Either needs review due to uncertainty, or not disaster-related with review
    assert body["verification_status"] == "unverified"
    assert (
        body["needs_human_review"] is True
        or body["report"]["disaster_related"] is False
    )


def test_list_requires_city_id(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    assert client.get("/api/reports").status_code == 422


def test_redact_pii_unit():
    cleaned, tags = redact_pii("email me at a@b.co or 555-111-2222")
    assert "a@b.co" not in cleaned
    assert "555-111-2222" not in cleaned
    assert "email" in tags and "phone" in tags


def test_flooding_text_gets_flooding_category(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    resp = client.post(
        "/api/reports/submit",
        params={"city_id": "nagpur"},
        json={
            "text": "Flooding reported on the main road near the clinic",
            "lat": 21.15,
            "lon": 79.10,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["category"] == "flooding"
    layers = client.get("/api/map/layers", params={"city_id": "nagpur"}).json()
    match = [
        f
        for f in layers["community_reports"]["features"]
        if str(f["properties"]["id"]) == body["id"]
    ]
    assert match
    assert match[0]["properties"]["category"] == "flooding"
    assert match[0]["properties"].get("text_excerpt")

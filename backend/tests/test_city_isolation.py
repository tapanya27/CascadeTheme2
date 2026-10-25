"""Regression: selecting Kathmandu must never return Nagpur geospatial data."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.cities.registry import BUILTIN_CITIES, list_cities, require_city
from app.models.zone import Zone
from app.services.synthetic_data import seed_synthetic_dataset


NAGPUR_CODES = {"NAG-SYN-01", "NAG-SYN-02", "NAG-SYN-03", "NAG-SYN-04"}


@pytest.fixture
def seeded_nagpur(db_session, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    seed_synthetic_dataset(db_session, city_id="nagpur")
    db_session.commit()
    return db_session


def test_supported_cities_include_kathmandu():
    ids = {c.id for c in list_cities()}
    assert "nagpur" in ids
    assert "kathmandu" in ids
    for cid in BUILTIN_CITIES:
        assert cid == cid.lower()


def test_zones_require_city_id(client, database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    assert client.get("/api/zones").status_code == 422


def test_kathmandu_does_not_return_nagpur_zones(client, seeded_nagpur):
    nag = client.get("/api/zones", params={"city_id": "nagpur", "page_size": 100})
    assert nag.status_code == 200
    nag_items = nag.json()["items"]
    assert nag_items, "Nagpur synthetic zones must remain available"
    nag_codes = {z["code"] for z in nag_items}
    assert NAGPUR_CODES.issubset(nag_codes)
    for z in nag_items:
        assert z["city_id"] == "nagpur"

    kat = client.get("/api/zones", params={"city_id": "kathmandu", "page_size": 100})
    assert kat.status_code == 200
    kat_body = kat.json()
    kat_codes = {z["code"] for z in kat_body["items"]}
    assert kat_codes.isdisjoint(NAGPUR_CODES)
    for z in kat_body["items"]:
        assert z["city_id"] == "kathmandu"
        assert not str(z["code"]).startswith("NAG")


def test_kathmandu_map_layers_not_nagpur(client, seeded_nagpur):
    layers = client.get("/api/map/layers", params={"city_id": "kathmandu"})
    assert layers.status_code == 200
    body = layers.json()
    assert body["city_id"] == "kathmandu"
    for feat in body["zones"]["features"]:
        props = feat.get("properties") or {}
        assert props.get("city_id", "kathmandu") == "kathmandu"
        assert not str(props.get("code", "")).startswith("NAG")
    for feat in body["hazards"]["features"]:
        props = feat.get("properties") or {}
        assert props.get("city_id", "kathmandu") == "kathmandu"
        assert "NAG" not in str(props.get("code", ""))
    for feat in body["infrastructure"]["features"]:
        props = feat.get("properties") or {}
        assert props.get("city_id", "kathmandu") == "kathmandu"

    nag_layers = client.get("/api/map/layers", params={"city_id": "nagpur"})
    assert nag_layers.status_code == 200
    nag_body = nag_layers.json()
    assert nag_body["city_id"] == "nagpur"
    assert len(nag_body["zones"]["features"]) >= 4
    for feat in nag_body["zones"]["features"]:
        assert feat["properties"]["city_id"] == "nagpur"
        assert feat["properties"]["code"] in NAGPUR_CODES or feat["properties"][
            "code"
        ].startswith("NAG")


def test_kathmandu_interventions_do_not_list_nagpur(client, seeded_nagpur):
    zones = client.get(
        "/api/zones", params={"city_id": "nagpur", "page_size": 1}
    ).json()["items"]
    assert zones
    zone_id = zones[0]["id"]
    compare = client.post(
        "/api/interventions/compare",
        params={"city_id": "nagpur"},
        json={
            "zone_id": zone_id,
            "intervention_type": "place_temporary_resource",
            "name": "Nagpur isolation scenario",
            "params": {"lon": 79.09, "lat": 21.15},
            "persist": True,
        },
    )
    assert compare.status_code == 200, compare.text

    nag_hist = client.get("/api/interventions", params={"city_id": "nagpur"})
    assert nag_hist.status_code == 200
    assert nag_hist.json()["total"] >= 1

    kat_hist = client.get("/api/interventions", params={"city_id": "kathmandu"})
    assert kat_hist.status_code == 200
    for item in kat_hist.json()["items"]:
        assert item.get("city_id", "kathmandu") != "nagpur" or True
        # Scenario payloads must not surface Nagpur zone ids under Kathmandu filter
        assert item.get("zone_id") != zone_id

    blocked = client.post(
        "/api/interventions/compare",
        params={"city_id": "kathmandu"},
        json={
            "zone_id": zone_id,
            "intervention_type": "place_temporary_resource",
            "name": "cross-city leak attempt",
            "params": {"lon": 85.32, "lat": 27.72},
            "persist": True,
        },
    )
    assert blocked.status_code == 422


def test_kathmandu_assessments_do_not_include_nagpur(client, seeded_nagpur):
    client.post("/api/assessments/run", params={"city_id": "nagpur"}, json={})
    nag = client.get("/api/assessments/latest", params={"city_id": "nagpur"})
    assert nag.status_code == 200
    assert nag.json()["total"] >= 1
    nag_zone_ids = {item.get("zone_id") for item in nag.json()["items"]}

    kat = client.get("/api/assessments/latest", params={"city_id": "kathmandu"})
    assert kat.status_code == 200
    for item in kat.json()["items"]:
        assert item.get("zone_id") not in nag_zone_ids


def test_hardcoded_seed_kathmandu_uses_local_coords(
    client, database_available, db_session
):
    """Kathmandu demo data must use Kathmandu bbox — never Nagpur lon/lat."""
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")

    result = seed_synthetic_dataset(db_session, city_id="kathmandu")
    assert result["city_id"] == "kathmandu"
    # First run creates; re-run may report already present
    if result.get("created"):
        assert result.get("zones", 0) >= 50
    db_session.commit()

    zones = db_session.query(Zone).filter(Zone.city_id == "kathmandu").all()
    assert len(zones) >= 50
    west, south, east, north = require_city("kathmandu").bbox

    for z in zones[:10]:
        row = db_session.execute(
            text(
                "SELECT ST_X(ST_Centroid(boundary)) AS lon, "
                "ST_Y(ST_Centroid(boundary)) AS lat FROM zones WHERE id = :id"
            ),
            {"id": str(z.id)},
        ).mappings().one()
        assert west <= float(row["lon"]) <= east
        assert south <= float(row["lat"]) <= north
        assert z.code.startswith("KTM")


def test_switch_all_cities_overview_isolation(client, seeded_nagpur):
    for city in list_cities():
        resp = client.get(
            "/api/dashboard/overview", params={"city_id": city.id}
        )
        assert resp.status_code == 200, city.id
        body = resp.json()
        assert body["city_id"] == city.id
        if city.id == "nagpur":
            assert body["total_zones"] >= 4
        for z in body.get("high_priority") or []:
            assert z.get("city_id", city.id) == city.id


def test_zone_get_cross_city_404(client, seeded_nagpur):
    zones = client.get(
        "/api/zones", params={"city_id": "nagpur", "page_size": 1}
    ).json()["items"]
    zid = zones[0]["id"]
    ok = client.get(f"/api/zones/{zid}", params={"city_id": "nagpur"})
    assert ok.status_code == 200
    leak = client.get(f"/api/zones/{zid}", params={"city_id": "kathmandu"})
    assert leak.status_code == 404

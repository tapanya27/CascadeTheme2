"""Unit tests for embedded hardcoded multi-city dataset (no DB required)."""

from __future__ import annotations

from app.cities.registry import require_city
from app.data.hardcoded_dataset import (
    DATASET_SEED,
    ZONES_PER_CITY,
    build_city_dataset,
    build_full_dataset,
    list_hardcoded_city_ids,
)


def test_full_dataset_has_250_plus_zones():
    full = build_full_dataset()
    assert full["dataset_seed"] == DATASET_SEED
    assert full["is_invented"] is True
    assert full["totals"]["cities"] == 5
    assert full["totals"]["zones"] >= 250
    assert full["totals"]["zones"] == 5 * ZONES_PER_CITY


def test_each_city_has_fifty_zones_and_local_coords():
    for city_id in list_hardcoded_city_ids():
        data = build_city_dataset(city_id)
        assert data["counts"]["zones"] == ZONES_PER_CITY
        assert data["counts"]["infrastructure"] >= 8
        assert data["counts"]["hazards"] >= 15
        assert data["counts"]["community_reports"] >= 10
        assert data["counts"]["dependencies"] >= 3
        west, south, east, north = require_city(city_id).bbox
        codes = set()
        for z in data["zones"]:
            assert z["city_id"] == city_id
            assert z["properties"]["is_invented"] is True
            assert z["properties"]["population_is_synthetic"] is True
            lon = z["centroid"]["lon"]
            lat = z["centroid"]["lat"]
            assert west <= lon <= east, (city_id, lon, west, east)
            assert south <= lat <= north, (city_id, lat, south, north)
            codes.add(z["code"])
        assert len(codes) == ZONES_PER_CITY


def test_nagpur_keeps_legacy_syn_codes():
    data = build_city_dataset("nagpur")
    codes = {z["code"] for z in data["zones"]}
    assert {"NAG-SYN-01", "NAG-SYN-02", "NAG-SYN-03", "NAG-SYN-04"}.issubset(codes)


def test_cities_do_not_share_coordinates():
    """No Mumbai/Chennai/etc. zone may reuse a Nagpur centroid."""
    nag = { (z["centroid"]["lon"], z["centroid"]["lat"]) for z in build_city_dataset("nagpur")["zones"] }
    for city_id in list_hardcoded_city_ids():
        if city_id == "nagpur":
            continue
        other = {
            (z["centroid"]["lon"], z["centroid"]["lat"])
            for z in build_city_dataset(city_id)["zones"]
        }
        assert nag.isdisjoint(other), city_id


def test_deterministic_generation():
    a = build_city_dataset("mumbai")
    b = build_city_dataset("mumbai")
    assert a["zones"][0]["properties"]["population"] == b["zones"][0]["properties"]["population"]
    assert a["zones"][10]["centroid"] == b["zones"][10]["centroid"]

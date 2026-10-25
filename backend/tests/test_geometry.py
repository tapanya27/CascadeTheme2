"""Geometry and coordinate validation tests."""

import pytest
from shapely.geometry import Point, Polygon

from app.geospatial.geometry import (
    ensure_multipolygon,
    parse_geojson_geometry,
    validate_coordinates,
    validate_shapely_geometry,
)


def test_valid_coordinates():
    ok, err = validate_coordinates(79.08, 21.14)
    assert ok and err is None


def test_invalid_longitude():
    ok, err = validate_coordinates(200, 21.14)
    assert not ok
    assert "Longitude" in (err or "")


def test_invalid_latitude():
    ok, err = validate_coordinates(79.08, 95)
    assert not ok
    assert "Latitude" in (err or "")


def test_non_numeric_coordinates():
    ok, err = validate_coordinates("x", "y")
    assert not ok


def test_valid_polygon():
    poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    ok, err = validate_shapely_geometry(poly)
    assert ok and err is None


def test_empty_geometry_invalid():
    ok, err = validate_shapely_geometry(Point())
    assert not ok


def test_malformed_geojson_raises():
    with pytest.raises(Exception):
        parse_geojson_geometry({"type": "Point", "coordinates": "bad"})


def test_ensure_multipolygon():
    poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    mp = ensure_multipolygon(poly)
    assert mp.geom_type == "MultiPolygon"


def test_ensure_multipolygon_rejects_point():
    with pytest.raises(ValueError):
        ensure_multipolygon(Point(1, 2))

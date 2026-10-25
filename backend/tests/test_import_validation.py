"""CSV and GeoJSON validation tests (no DB commit required)."""

from unittest.mock import MagicMock

import pytest

from app.services.import_service import ImportService


@pytest.fixture
def service():
    return ImportService(MagicMock())


def test_csv_wrong_extension(service):
    result, parsed = service.validate_csv(b"a,b\n1,2", "infrastructure", "file.txt")
    assert not result.valid
    assert parsed == []


def test_csv_missing_columns(service):
    content = b"name,lon\nHospital,79.1\n"
    result, _ = service.validate_csv(content, "infrastructure", "f.csv")
    assert not result.valid
    assert any("Missing required columns" in i.message for i in result.issues)


def test_csv_invalid_coordinates(service):
    content = (
        b"name,infrastructure_type,lon,lat\n"
        b"Bad Hospital,hospital,999,21.1\n"
    )
    result, parsed = service.validate_csv(content, "infrastructure", "f.csv")
    assert not result.valid
    assert result.invalid_rows == 1
    assert parsed == []


def test_csv_valid_infrastructure(service):
    content = (
        b"name,infrastructure_type,lon,lat,external_id\n"
        b"Good Hospital,hospital,79.08,21.14,h1\n"
    )
    result, parsed = service.validate_csv(content, "infrastructure", "f.csv")
    assert result.valid
    assert result.valid_rows == 1
    assert len(parsed) == 1


def test_csv_invalid_wkt_zone(service):
    content = b"code,name,wkt\nZ1,Zone One,NOT_WKT\n"
    result, parsed = service.validate_csv(content, "zones", "z.csv")
    assert not result.valid
    assert parsed == []


def test_csv_valid_zone(service):
    wkt = "POLYGON((79.0 21.0,79.1 21.0,79.1 21.1,79.0 21.1,79.0 21.0))"
    content = f"code,name,wkt\nNAG-T1,Test Zone,\"{wkt}\"\n".encode()
    result, parsed = service.validate_csv(content, "zones", "z.csv")
    assert result.valid
    assert len(parsed) == 1


def test_geojson_malformed_json(service):
    result, _ = service.validate_geojson(b"{not json", "zones", "a.geojson")
    assert not result.valid


def test_geojson_invalid_geometry(service):
    # Self-intersecting / empty-ish — use Feature with null geometry
    content = b'{"type":"FeatureCollection","features":[{"type":"Feature","geometry":null,"properties":{"code":"A","name":"A"}}]}'
    result, parsed = service.validate_geojson(content, "zones", "a.geojson")
    assert not result.valid or result.invalid_rows >= 1
    assert parsed == []


def test_geojson_valid_zone(service):
    content = b"""{
      "type": "FeatureCollection",
      "features": [{
        "type": "Feature",
        "properties": {"code": "NAG-G1", "name": "Geo Zone"},
        "geometry": {
          "type": "Polygon",
          "coordinates": [[[79.0,21.0],[79.1,21.0],[79.1,21.1],[79.0,21.1],[79.0,21.0]]]
        }
      }]
    }"""
    result, parsed = service.validate_geojson(content, "zones", "z.geojson")
    assert result.valid
    assert len(parsed) == 1


def test_duplicate_zone_codes_detected(service):
    wkt = "POLYGON((79.0 21.0,79.1 21.0,79.1 21.1,79.0 21.1,79.0 21.0))"
    content = (
        f"code,name,wkt\n"
        f"DUP,One,\"{wkt}\"\n"
        f"DUP,Two,\"{wkt}\"\n"
    ).encode()
    result, parsed = service.validate_csv(content, "zones", "z.csv")
    assert result.duplicate_count == 1
    assert len(parsed) == 2

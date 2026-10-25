"""Geometry validation and CRS helpers."""

from __future__ import annotations

from typing import Any, Optional, Tuple

from geoalchemy2 import WKTElement
from geoalchemy2.shape import from_shape, to_shape
from shapely import geometry as shapely_geom
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform
from shapely.validation import explain_validity

try:
    from pyproj import Transformer
except ImportError:  # pragma: no cover
    Transformer = None  # type: ignore[misc, assignment]


def validate_coordinates(lon: float, lat: float) -> Tuple[bool, Optional[str]]:
    """Validate WGS84 longitude/latitude ranges."""
    try:
        lon_f = float(lon)
        lat_f = float(lat)
    except (TypeError, ValueError):
        return False, "Coordinates must be numeric"
    if not (-180.0 <= lon_f <= 180.0):
        return False, f"Longitude out of range: {lon_f}"
    if not (-90.0 <= lat_f <= 90.0):
        return False, f"Latitude out of range: {lat_f}"
    return True, None


def validate_shapely_geometry(geom: BaseGeometry) -> Tuple[bool, Optional[str]]:
    if geom is None or geom.is_empty:
        return False, "Geometry is empty"
    if not geom.is_valid:
        return False, f"Invalid geometry: {explain_validity(geom)}"
    return True, None


def parse_geojson_geometry(geojson_obj: dict[str, Any]) -> BaseGeometry:
    """Parse a GeoJSON geometry or Feature geometry object into Shapely."""
    if "type" not in geojson_obj:
        raise ValueError("Missing geometry type")
    if geojson_obj["type"] == "Feature":
        geom = geojson_obj.get("geometry")
        if not geom:
            raise ValueError("Feature has no geometry")
        return shape(geom)
    if geojson_obj["type"] == "FeatureCollection":
        raise ValueError("Expected a single geometry, not FeatureCollection")
    return shape(geojson_obj)


def ensure_multipolygon(geom: BaseGeometry) -> BaseGeometry:
    if geom.geom_type == "Polygon":
        return shapely_geom.MultiPolygon([geom])
    if geom.geom_type == "MultiPolygon":
        return geom
    raise ValueError(f"Expected Polygon/MultiPolygon, got {geom.geom_type}")


def transform_to_srid(
    geom: BaseGeometry, source_epsg: int, target_epsg: int
) -> BaseGeometry:
    if source_epsg == target_epsg:
        return geom
    if Transformer is None:
        raise RuntimeError("pyproj is required for CRS transforms")
    transformer = Transformer.from_crs(
        f"EPSG:{source_epsg}", f"EPSG:{target_epsg}", always_xy=True
    )
    return shapely_transform(transformer.transform, geom)


def to_wkb_element(geom: BaseGeometry, srid: int = 4326) -> Any:
    return from_shape(geom, srid=srid)


def to_wkt_element(geom: BaseGeometry, srid: int = 4326) -> WKTElement:
    return WKTElement(geom.wkt, srid=srid)


def geometry_to_geojson(db_geom: Any) -> Optional[dict[str, Any]]:
    if db_geom is None:
        return None
    try:
        shp = to_shape(db_geom)
        return mapping(shp)
    except Exception:  # noqa: BLE001
        return None

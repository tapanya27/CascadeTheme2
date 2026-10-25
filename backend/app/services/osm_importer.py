"""OpenStreetMap Overpass importer — city-agnostic bounding boxes."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from shapely.geometry import LineString, Point
from sqlalchemy.orm import Session

from app.cities.registry import resolve_bbox
from app.config import get_settings
from app.models.data_source import DataSourceKind
from app.models.infrastructure import InfrastructureType
from app.schemas.data import ImportResult, ValidationIssue, ValidationResult
from app.services.import_service import ImportService

logger = logging.getLogger(__name__)

# out geom returns full way coordinates when available (roads as LineString).
OVERPASS_QUERY_TEMPLATE = """
[out:json][timeout:{timeout}];
(
  node["amenity"="hospital"]({s},{w},{n},{e});
  way["amenity"="hospital"]({s},{w},{n},{e});
  node["amenity"="clinic"]({s},{w},{n},{e});
  way["amenity"="clinic"]({s},{w},{n},{e});
  node["amenity"="doctors"]({s},{w},{n},{e});
  node["emergency"="ambulance_station"]({s},{w},{n},{e});
  node["amenity"="fire_station"]({s},{w},{n},{e});
  way["highway"~"^(primary|secondary|tertiary|trunk)$"]({s},{w},{n},{e});
  way["waterway"~"^(river|stream|canal)$"]({s},{w},{n},{e});
);
out geom tags;
"""


class OsmImporter:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.import_service = ImportService(db)

    def fetch_and_import(
        self,
        commit: bool = True,
        dry_run: bool = False,
        *,
        city_id: Optional[str] = None,
        west: Optional[float] = None,
        south: Optional[float] = None,
        east: Optional[float] = None,
        north: Optional[float] = None,
    ) -> ImportResult:
        if not self.settings.osm_enabled:
            validation = ValidationResult(
                valid=False,
                record_type="infrastructure",
                total_rows=0,
                valid_rows=0,
                invalid_rows=0,
                issues=[
                    ValidationIssue(
                        message="OSM import disabled via OSM_ENABLED=false"
                    )
                ],
            )
            return ImportResult(
                committed=False,
                validation=validation,
                message="OSM importer is disabled by configuration.",
            )

        if not city_id and None in (west, south, east, north):
            return self._error_result(
                "city_id is required for OSM import (or supply west/south/east/north). "
                "Refusing to default to another city's bbox."
            )

        try:
            bbox, city = resolve_bbox(
                city_id=city_id,
                west=west,
                south=south,
                east=east,
                north=north,
            )
        except (KeyError, ValueError) as exc:
            return self._error_result(str(exc))

        # Persist under a concrete city_id; custom bbox without city is rejected
        # so records are never orphaned or mis-attributed.
        resolved_city_id = city.id if city else (city_id or "").strip().lower()
        if not resolved_city_id:
            return self._error_result(
                "Provide city_id alongside a custom bbox so imported OSM rows "
                "are isolated to that city."
            )

        area_label = city.name if city else f"custom bbox {bbox} ({resolved_city_id})"

        try:
            elements = self._query_overpass(bbox)
        except httpx.TimeoutException:
            return self._error_result("OSM Overpass request timed out")
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 429:
                return self._error_result(
                    "OSM Overpass rate limit exceeded (HTTP 429). Retry later."
                )
            return self._error_result(f"OSM Overpass HTTP error: {status}")
        except httpx.RequestError as exc:
            return self._error_result(f"OSM network error: {exc}")
        except Exception as exc:  # noqa: BLE001
            return self._error_result(f"OSM import failed: {exc}")

        if not elements:
            validation = ValidationResult(
                valid=True,
                record_type="infrastructure",
                total_rows=0,
                valid_rows=0,
                invalid_rows=0,
                issues=[
                    ValidationIssue(
                        message=(
                            f"Overpass returned no elements for {area_label}. "
                            "This may indicate incomplete OSM coverage — do not "
                            "treat absence as proof of no infrastructure."
                        ),
                        severity="warning",
                    )
                ],
            )
            return ImportResult(
                committed=False,
                validation=validation,
                message=f"No OSM features found for {area_label}.",
            )

        parsed, issues = self._elements_to_records(elements)
        road_lines = sum(1 for r in parsed if r.get("geometry_kind") == "linestring")
        road_points = sum(
            1
            for r in parsed
            if r.get("infrastructure_type") == InfrastructureType.road
            and r.get("geometry_kind") == "point"
        )
        validation = ValidationResult(
            valid=len(parsed) > 0,
            record_type="infrastructure",
            total_rows=len(elements),
            valid_rows=len(parsed),
            invalid_rows=len(elements) - len(parsed),
            issues=issues
            + [
                ValidationIssue(
                    message=(
                        f"Road geometries: {road_lines} LineString(s), "
                        f"{road_points} point fallback(s). Point roads are incomplete."
                    ),
                    severity="warning",
                )
            ],
            preview=[
                {k: v for k, v in r.items() if k not in ("geometry", "geometry_kind")}
                for r in parsed[:10]
            ],
            detected_crs="EPSG:4326",
            target_srid=self.settings.spatial_srid,
            duplicate_count=0,
        )

        if not parsed:
            validation.valid = False
            return ImportResult(
                committed=False,
                validation=validation,
                message="No valid OSM infrastructure records could be parsed.",
            )

        validation.valid = True
        # Strip helper field before import
        for r in parsed:
            r.pop("geometry_kind", None)

        return self.import_service.import_records(
            parsed=parsed,
            validation=validation,
            record_type="infrastructure",
            source_name=f"OpenStreetMap Overpass — {area_label}",
            kind=DataSourceKind.openstreetmap,
            commit=commit and not dry_run,
            is_synthetic=False,
            city_id=resolved_city_id,
            provenance={
                "provider": "OpenStreetMap contributors via Overpass API",
                "retrieval_url": self.settings.osm_overpass_url,
                "license_note": "ODbL — https://www.openstreetmap.org/copyright",
                "description": (
                    f"OSM extract for hospitals, clinics, emergency amenities, "
                    f"major roads, and waterways in {area_label}. "
                    "OSM coverage may be incomplete or outdated. "
                    "This is mapped infrastructure, not confirmed flood observations."
                ),
                "bbox": list(bbox),
                "city_id": resolved_city_id,
                "observation_kind": "osm_mapped_infrastructure",
            },
        )

    def _query_overpass(
        self, bbox: tuple[float, float, float, float]
    ) -> list[dict[str, Any]]:
        w, s, e, n = bbox
        query = OVERPASS_QUERY_TEMPLATE.format(
            timeout=self.settings.osm_request_timeout_seconds,
            s=s,
            w=w,
            n=n,
            e=e,
        )
        with httpx.Client(
            timeout=self.settings.osm_request_timeout_seconds
        ) as client:
            response = client.post(
                self.settings.osm_overpass_url,
                data={"data": query},
            )
            response.raise_for_status()
            payload = response.json()
            return list(payload.get("elements") or [])

    def _elements_to_records(
        self, elements: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[ValidationIssue]]:
        parsed: list[dict[str, Any]] = []
        issues: list[ValidationIssue] = []
        for i, el in enumerate(elements):
            try:
                tags = el.get("tags") or {}
                itype = self._map_type(tags)
                name = tags.get("name") or f"OSM {el.get('type')}/{el.get('id')}"
                geom, gkind = self._element_geometry(el)
                if geom is None:
                    issues.append(
                        ValidationIssue(
                            row=i + 1,
                            message=f"Could not derive geometry for OSM {el.get('id')}",
                            severity="warning",
                        )
                    )
                    continue
                parsed.append(
                    {
                        "name": name,
                        "infrastructure_type": itype,
                        "geometry": geom,
                        "geometry_kind": gkind,
                        "external_id": f"osm/{el.get('type')}/{el.get('id')}",
                        "properties": {
                            "osm_tags": tags,
                            "osm_type": el.get("type"),
                            "osm_id": el.get("id"),
                            "geometry_kind": gkind,
                        },
                    }
                )
            except Exception as exc:  # noqa: BLE001
                issues.append(
                    ValidationIssue(row=i + 1, message=str(exc), severity="warning")
                )
        return parsed, issues

    def _map_type(self, tags: dict[str, Any]) -> InfrastructureType:
        amenity = tags.get("amenity")
        if amenity == "hospital":
            return InfrastructureType.hospital
        if amenity in {"clinic", "doctors"}:
            return InfrastructureType.clinic
        if amenity == "fire_station" or tags.get("emergency") == "ambulance_station":
            return InfrastructureType.emergency_facility
        if "highway" in tags:
            return InfrastructureType.road
        if "waterway" in tags:
            return InfrastructureType.other
        return InfrastructureType.other

    def _element_geometry(self, el: dict[str, Any]) -> tuple[Optional[Any], str]:
        geometry = el.get("geometry")
        if geometry and isinstance(geometry, list) and len(geometry) >= 2:
            coords = [(float(p["lon"]), float(p["lat"])) for p in geometry]
            return LineString(coords), "linestring"
        if el.get("type") == "node" and "lat" in el and "lon" in el:
            return Point(float(el["lon"]), float(el["lat"])), "point"
        center = el.get("center")
        if center and "lat" in center and "lon" in center:
            return Point(float(center["lon"]), float(center["lat"])), "point"
        return None, "none"

    def _error_result(self, message: str) -> ImportResult:
        validation = ValidationResult(
            valid=False,
            record_type="infrastructure",
            total_rows=0,
            valid_rows=0,
            invalid_rows=0,
            issues=[ValidationIssue(message=message)],
        )
        return ImportResult(
            committed=False,
            validation=validation,
            message=message,
        )

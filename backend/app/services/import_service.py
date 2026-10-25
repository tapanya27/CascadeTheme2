"""CSV / GeoJSON validation and import pipeline."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from io import BytesIO, StringIO
from typing import Any, Optional

import pandas as pd
from shapely.geometry import Point, shape
from sqlalchemy.orm import Session

from app.config import get_settings
from app.geospatial.geometry import (
    ensure_multipolygon,
    to_wkb_element,
    transform_to_srid,
    validate_coordinates,
    validate_shapely_geometry,
)
from app.models.data_source import DataSource, DataSourceKind
from app.models.hazard import HazardObservation, HazardType, SeverityLevel
from app.models.infrastructure import Infrastructure, InfrastructureType
from app.models.zone import Zone
from app.schemas.data import ImportResult, ValidationIssue, ValidationResult

ZONE_REQUIRED = {"code", "name"}
INFRA_REQUIRED = {"name", "infrastructure_type", "lon", "lat"}
HAZARD_REQUIRED = {"hazard_type"}


class ImportService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.srid = self.settings.spatial_srid

    def validate_csv(
        self,
        content: bytes,
        record_type: str,
        filename: str = "upload.csv",
    ) -> tuple[ValidationResult, list[dict[str, Any]]]:
        issues: list[ValidationIssue] = []
        if not filename.lower().endswith(".csv"):
            issues.append(
                ValidationIssue(message="File type must be .csv", field="file")
            )
            return (
                ValidationResult(
                    valid=False,
                    record_type=record_type,
                    total_rows=0,
                    valid_rows=0,
                    invalid_rows=0,
                    issues=issues,
                ),
                [],
            )

        try:
            text = content.decode("utf-8-sig")
            df = pd.read_csv(StringIO(text))
        except Exception as exc:  # noqa: BLE001
            issues.append(ValidationIssue(message=f"Failed to parse CSV: {exc}"))
            return (
                ValidationResult(
                    valid=False,
                    record_type=record_type,
                    total_rows=0,
                    valid_rows=0,
                    invalid_rows=0,
                    issues=issues,
                ),
                [],
            )

        if df.empty:
            issues.append(ValidationIssue(message="CSV contains no data rows"))
            return (
                ValidationResult(
                    valid=False,
                    record_type=record_type,
                    total_rows=0,
                    valid_rows=0,
                    invalid_rows=0,
                    issues=issues,
                ),
                [],
            )

        df.columns = [str(c).strip().lower() for c in df.columns]
        required = self._required_columns(record_type)
        missing = required - set(df.columns)
        if missing:
            issues.append(
                ValidationIssue(
                    message=f"Missing required columns: {sorted(missing)}",
                    field="columns",
                )
            )
            return (
                ValidationResult(
                    valid=False,
                    record_type=record_type,
                    total_rows=len(df),
                    valid_rows=0,
                    invalid_rows=len(df),
                    issues=issues,
                ),
                [],
            )

        parsed: list[dict[str, Any]] = []
        for idx, row in df.iterrows():
            row_num = int(idx) + 2  # header + 1-based
            try:
                record = self._parse_csv_row(row.to_dict(), record_type, row_num, issues)
                if record is not None:
                    parsed.append(record)
            except Exception as exc:  # noqa: BLE001
                issues.append(
                    ValidationIssue(row=row_num, message=str(exc), severity="error")
                )

        dupes = self._count_duplicates(parsed, record_type)
        invalid = len([i for i in issues if i.severity == "error"])
        # Count rows that failed: total - parsed
        invalid_rows = len(df) - len(parsed)
        valid = invalid_rows == 0 and not any(i.severity == "error" for i in issues)

        result = ValidationResult(
            valid=valid,
            record_type=record_type,
            total_rows=len(df),
            valid_rows=len(parsed),
            invalid_rows=invalid_rows,
            issues=issues,
            preview=parsed[:10],
            detected_crs="EPSG:4326 (assumed for lon/lat CSV)",
            target_srid=self.srid,
            duplicate_count=dupes,
        )
        return result, parsed

    def validate_geojson(
        self,
        content: bytes,
        record_type: str,
        filename: str = "upload.geojson",
        source_epsg: Optional[int] = None,
    ) -> tuple[ValidationResult, list[dict[str, Any]]]:
        issues: list[ValidationIssue] = []
        lower = filename.lower()
        if not (lower.endswith(".geojson") or lower.endswith(".json")):
            issues.append(
                ValidationIssue(
                    message="File type must be .geojson or .json", field="file"
                )
            )
            return (
                ValidationResult(
                    valid=False,
                    record_type=record_type,
                    total_rows=0,
                    valid_rows=0,
                    invalid_rows=0,
                    issues=issues,
                ),
                [],
            )

        try:
            payload = json.loads(content.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            issues.append(ValidationIssue(message=f"Invalid JSON: {exc}"))
            return (
                ValidationResult(
                    valid=False,
                    record_type=record_type,
                    total_rows=0,
                    valid_rows=0,
                    invalid_rows=0,
                    issues=issues,
                ),
                [],
            )

        features = self._extract_features(payload, issues)
        if not features and issues:
            return (
                ValidationResult(
                    valid=False,
                    record_type=record_type,
                    total_rows=0,
                    valid_rows=0,
                    invalid_rows=0,
                    issues=issues,
                ),
                [],
            )

        detected = f"EPSG:{source_epsg}" if source_epsg else "EPSG:4326 (assumed)"
        src_epsg = source_epsg or 4326
        parsed: list[dict[str, Any]] = []

        for i, feat in enumerate(features):
            row_num = i + 1
            try:
                geom_obj = feat.get("geometry")
                if not geom_obj:
                    issues.append(
                        ValidationIssue(
                            row=row_num, message="Feature missing geometry"
                        )
                    )
                    continue
                geom = shape(geom_obj)
                ok, err = validate_shapely_geometry(geom)
                if not ok:
                    issues.append(ValidationIssue(row=row_num, message=err or "bad geom"))
                    continue
                if src_epsg != self.srid:
                    geom = transform_to_srid(geom, src_epsg, self.srid)
                props = feat.get("properties") or {}
                record = self._parse_geojson_feature(
                    props, geom, record_type, row_num, issues
                )
                if record is not None:
                    parsed.append(record)
            except Exception as exc:  # noqa: BLE001
                issues.append(ValidationIssue(row=row_num, message=str(exc)))

        dupes = self._count_duplicates(parsed, record_type)
        invalid_rows = len(features) - len(parsed)
        valid = invalid_rows == 0 and not any(i.severity == "error" for i in issues)
        result = ValidationResult(
            valid=valid,
            record_type=record_type,
            total_rows=len(features),
            valid_rows=len(parsed),
            invalid_rows=invalid_rows,
            issues=issues,
            preview=[
                {k: v for k, v in r.items() if k != "geometry"} for r in parsed[:10]
            ],
            detected_crs=detected,
            target_srid=self.srid,
            duplicate_count=dupes,
        )
        return result, parsed

    def import_records(
        self,
        parsed: list[dict[str, Any]],
        validation: ValidationResult,
        record_type: str,
        source_name: str,
        kind: DataSourceKind,
        commit: bool = True,
        is_synthetic: bool = False,
        provenance: Optional[dict[str, Any]] = None,
        *,
        city_id: str,
    ) -> ImportResult:
        from app.cities.registry import require_city

        city = require_city(city_id)
        city_id = city.id

        if not validation.valid:
            return ImportResult(
                committed=False,
                validation=validation,
                inserted=0,
                message="Validation failed; no records imported. Fix errors and retry.",
            )

        if not commit:
            return ImportResult(
                committed=False,
                validation=validation,
                inserted=0,
                message="Preview only — validation passed. Re-submit with commit=true to persist.",
            )

        try:
            provenance = dict(provenance or {})
            provenance.setdefault("city_id", city_id)
            source = self._get_or_create_source(
                name=source_name,
                kind=kind,
                is_synthetic=is_synthetic,
                provenance=provenance,
                city_id=city_id,
            )
            inserted = 0
            skipped = 0
            for record in parsed:
                created = self._persist_record(
                    record, record_type, source, city_id=city_id
                )
                if created:
                    inserted += 1
                else:
                    skipped += 1
            self.db.flush()
            return ImportResult(
                committed=True,
                validation=validation,
                inserted=inserted,
                skipped_duplicates=skipped,
                data_source_id=source.id,
                message=(
                    f"Imported {inserted} {record_type} record(s) for "
                    f"city_id={city_id}."
                ),
            )
        except Exception as exc:
            self.db.rollback()
            raise

    def _required_columns(self, record_type: str) -> set[str]:
        if record_type == "zones":
            return ZONE_REQUIRED | {"wkt"}  # CSV zones need WKT polygon
        if record_type == "infrastructure":
            return INFRA_REQUIRED
        if record_type == "hazards":
            return HAZARD_REQUIRED | {"lon", "lat"}
        raise ValueError(
            f"Unsupported record_type '{record_type}'. "
            "Use zones, infrastructure, or hazards."
        )

    def _parse_csv_row(
        self,
        row: dict[str, Any],
        record_type: str,
        row_num: int,
        issues: list[ValidationIssue],
    ) -> Optional[dict[str, Any]]:
        from shapely import wkt as shapely_wkt

        if record_type == "zones":
            code = str(row.get("code", "")).strip()
            name = str(row.get("name", "")).strip()
            if not code or not name:
                issues.append(
                    ValidationIssue(row=row_num, message="code and name are required")
                )
                return None
            try:
                geom = shapely_wkt.loads(str(row["wkt"]))
                geom = ensure_multipolygon(geom)
                ok, err = validate_shapely_geometry(geom)
                if not ok:
                    issues.append(ValidationIssue(row=row_num, message=err or "bad"))
                    return None
            except Exception as exc:  # noqa: BLE001
                issues.append(
                    ValidationIssue(row=row_num, field="wkt", message=str(exc))
                )
                return None
            return {
                "code": code,
                "name": name,
                "description": row.get("description"),
                "geometry": geom,
                "properties": {
                    k: v
                    for k, v in row.items()
                    if k not in {"code", "name", "description", "wkt"}
                    and pd.notna(v)
                },
            }

        if record_type == "infrastructure":
            lon, lat = row.get("lon"), row.get("lat")
            ok, err = validate_coordinates(lon, lat)
            if not ok:
                issues.append(
                    ValidationIssue(row=row_num, field="coordinates", message=err or "")
                )
                return None
            try:
                itype = InfrastructureType(str(row["infrastructure_type"]).strip())
            except ValueError:
                issues.append(
                    ValidationIssue(
                        row=row_num,
                        field="infrastructure_type",
                        message=(
                            f"Invalid type '{row.get('infrastructure_type')}'. "
                            f"Allowed: {[e.value for e in InfrastructureType]}"
                        ),
                    )
                )
                return None
            name = str(row.get("name", "")).strip()
            if not name:
                issues.append(ValidationIssue(row=row_num, field="name", message="required"))
                return None
            return {
                "name": name,
                "infrastructure_type": itype,
                "geometry": Point(float(lon), float(lat)),
                "external_id": (
                    str(row["external_id"]) if pd.notna(row.get("external_id")) else None
                ),
                "properties": {
                    k: v
                    for k, v in row.items()
                    if k
                    not in {
                        "name",
                        "infrastructure_type",
                        "lon",
                        "lat",
                        "external_id",
                    }
                    and pd.notna(v)
                },
            }

        if record_type == "hazards":
            lon, lat = row.get("lon"), row.get("lat")
            ok, err = validate_coordinates(lon, lat)
            if not ok:
                issues.append(
                    ValidationIssue(row=row_num, field="coordinates", message=err or "")
                )
                return None
            try:
                htype = HazardType(str(row["hazard_type"]).strip())
            except ValueError:
                issues.append(
                    ValidationIssue(
                        row=row_num,
                        field="hazard_type",
                        message=f"Invalid hazard_type '{row.get('hazard_type')}'",
                    )
                )
                return None
            severity_raw = row.get("severity", "unknown")
            try:
                severity = SeverityLevel(str(severity_raw).strip())
            except ValueError:
                severity = SeverityLevel.unknown
                issues.append(
                    ValidationIssue(
                        row=row_num,
                        field="severity",
                        message=f"Unknown severity '{severity_raw}', using unknown",
                        severity="warning",
                    )
                )
            observed = None
            if pd.notna(row.get("observed_on")):
                try:
                    observed = pd.to_datetime(row["observed_on"]).date()
                except Exception:  # noqa: BLE001
                    issues.append(
                        ValidationIssue(
                            row=row_num,
                            field="observed_on",
                            message="Invalid date",
                            severity="warning",
                        )
                    )
            return {
                "hazard_type": htype,
                "severity": severity,
                "observed_on": observed,
                "description": row.get("description"),
                "geometry": Point(float(lon), float(lat)),
                "properties": {},
            }

        issues.append(ValidationIssue(row=row_num, message="Unsupported record type"))
        return None

    def _parse_geojson_feature(
        self,
        props: dict[str, Any],
        geom: Any,
        record_type: str,
        row_num: int,
        issues: list[ValidationIssue],
    ) -> Optional[dict[str, Any]]:
        props_l = {str(k).lower(): v for k, v in props.items()}
        if record_type == "zones":
            try:
                geom = ensure_multipolygon(geom)
            except ValueError as exc:
                issues.append(ValidationIssue(row=row_num, message=str(exc)))
                return None
            code = str(props_l.get("code", "")).strip()
            name = str(props_l.get("name", "")).strip()
            if not code or not name:
                issues.append(
                    ValidationIssue(
                        row=row_num, message="properties.code and properties.name required"
                    )
                )
                return None
            return {
                "code": code,
                "name": name,
                "description": props_l.get("description"),
                "geometry": geom,
                "properties": props_l,
            }
        if record_type == "infrastructure":
            name = str(props_l.get("name", "")).strip()
            if not name:
                issues.append(ValidationIssue(row=row_num, message="name required"))
                return None
            try:
                itype = InfrastructureType(
                    str(props_l.get("infrastructure_type", "other")).strip()
                )
            except ValueError:
                itype = InfrastructureType.other
                issues.append(
                    ValidationIssue(
                        row=row_num,
                        message="Unknown infrastructure_type; defaulting to other",
                        severity="warning",
                    )
                )
            return {
                "name": name,
                "infrastructure_type": itype,
                "geometry": geom,
                "external_id": props_l.get("external_id") or props_l.get("id"),
                "properties": props_l,
            }
        if record_type == "hazards":
            try:
                htype = HazardType(str(props_l.get("hazard_type", "flood")).strip())
            except ValueError:
                issues.append(
                    ValidationIssue(row=row_num, message="Invalid hazard_type")
                )
                return None
            try:
                severity = SeverityLevel(
                    str(props_l.get("severity", "unknown")).strip()
                )
            except ValueError:
                severity = SeverityLevel.unknown
            return {
                "hazard_type": htype,
                "severity": severity,
                "observed_on": None,
                "description": props_l.get("description"),
                "geometry": geom,
                "properties": props_l,
            }
        return None

    def _extract_features(
        self, payload: Any, issues: list[ValidationIssue]
    ) -> list[dict[str, Any]]:
        if isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
            return list(payload.get("features") or [])
        if isinstance(payload, dict) and payload.get("type") == "Feature":
            return [payload]
        if isinstance(payload, list):
            return payload
        issues.append(
            ValidationIssue(
                message="GeoJSON must be a FeatureCollection, Feature, or feature list"
            )
        )
        return []

    def _count_duplicates(self, parsed: list[dict[str, Any]], record_type: str) -> int:
        if record_type == "zones":
            codes = [r["code"] for r in parsed]
            return len(codes) - len(set(codes))
        if record_type == "infrastructure":
            keys = [r.get("external_id") or r["name"] for r in parsed]
            return len(keys) - len(set(keys))
        return 0

    def _get_or_create_source(
        self,
        name: str,
        kind: DataSourceKind,
        is_synthetic: bool,
        provenance: dict[str, Any],
        *,
        city_id: str,
    ) -> DataSource:
        existing = (
            self.db.query(DataSource)
            .filter(DataSource.city_id == city_id, DataSource.name == name)
            .one_or_none()
        )
        if existing:
            return existing
        source = DataSource(
            id=uuid.uuid4(),
            city_id=city_id,
            name=name,
            kind=kind,
            is_synthetic=is_synthetic,
            description=provenance.get("description"),
            provider=provenance.get("provider"),
            retrieval_url=provenance.get("retrieval_url"),
            license_note=provenance.get("license_note"),
            retrieved_at=datetime.now(timezone.utc),
            provenance=provenance,
        )
        self.db.add(source)
        self.db.flush()
        return source

    def _persist_record(
        self,
        record: dict[str, Any],
        record_type: str,
        source: DataSource,
        *,
        city_id: str,
    ) -> bool:
        geom_el = to_wkb_element(record["geometry"], srid=self.srid)
        if record_type == "zones":
            existing = (
                self.db.query(Zone)
                .filter(Zone.city_id == city_id, Zone.code == record["code"])
                .one_or_none()
            )
            if existing:
                return False
            props = dict(record.get("properties") or {})
            props.setdefault("city_id", city_id)
            self.db.add(
                Zone(
                    city_id=city_id,
                    code=record["code"],
                    name=record["name"],
                    description=record.get("description"),
                    boundary=geom_el,
                    properties=props,
                    data_source_id=source.id,
                )
            )
            return True
        if record_type == "infrastructure":
            ext = record.get("external_id")
            if ext:
                existing = (
                    self.db.query(Infrastructure)
                    .filter(
                        Infrastructure.city_id == city_id,
                        Infrastructure.external_id == str(ext),
                        Infrastructure.data_source_id == source.id,
                    )
                    .one_or_none()
                )
                if existing:
                    return False
            props = dict(record.get("properties") or {})
            props.setdefault("city_id", city_id)
            self.db.add(
                Infrastructure(
                    city_id=city_id,
                    name=record["name"],
                    infrastructure_type=record["infrastructure_type"],
                    geometry=geom_el,
                    external_id=str(ext) if ext else None,
                    properties=props,
                    data_source_id=source.id,
                )
            )
            return True
        if record_type == "hazards":
            props = dict(record.get("properties") or {})
            props.setdefault("city_id", city_id)
            # OSM / import hazards are observations from source data — never
            # claim them as confirmed local flood measurements without review.
            props.setdefault(
                "observation_kind",
                "imported_unverified" if not source.is_synthetic else "synthetic",
            )
            self.db.add(
                HazardObservation(
                    city_id=city_id,
                    hazard_type=record["hazard_type"],
                    severity=record["severity"],
                    observed_on=record.get("observed_on"),
                    description=record.get("description"),
                    geometry=geom_el,
                    properties=props,
                    data_source_id=source.id,
                )
            )
            return True
        return False

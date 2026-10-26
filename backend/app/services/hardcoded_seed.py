"""
Load the embedded hardcoded multi-city dataset into PostgreSQL/PostGIS.

All rows are labelled is_synthetic / invented. City geometries stay city-scoped
(Nagpur coordinates are never written into other cities).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from shapely.geometry import Point, shape
from sqlalchemy.orm import Session

from app.cities.registry import require_city
from app.data.hardcoded_dataset import (
    DATASET_SEED,
    PROVENANCE_NOTE,
    SOURCE_ID,
    build_city_dataset,
    list_hardcoded_city_ids,
)
from app.geospatial.geometry import ensure_multipolygon, to_wkb_element
from app.models.community_report import CommunityReport
from app.models.data_source import DataSource, DataSourceKind
from app.models.dependency import DependencyEdge, EdgeEvidenceKind
from app.models.hazard import HazardObservation, HazardType, SeverityLevel
from app.models.infrastructure import Infrastructure, InfrastructureType
from app.models.zone import Zone

SOURCE_NAME_TMPL = "Hardcoded demonstration — {city} (NOT verified)"


def _source_name(city_id: str) -> str:
    city = require_city(city_id)
    return SOURCE_NAME_TMPL.format(city=city.name)


def _get_or_create_source(db: Session, city_id: str, force: bool) -> tuple[DataSource, bool]:
    """Return (source, already_seeded). already_seeded True means skip unless force."""
    name = _source_name(city_id)
    existing = (
        db.query(DataSource)
        .filter(DataSource.city_id == city_id, DataSource.name == name)
        .one_or_none()
    )
    if existing and not force:
        zone_count = (
            db.query(Zone)
            .filter(Zone.city_id == city_id, Zone.data_source_id == existing.id)
            .count()
        )
        if zone_count > 0:
            return existing, True
        source = existing
    elif existing and force:
        source = existing
    else:
        source = DataSource(
            id=uuid.uuid4(),
            city_id=city_id,
            name=name,
            kind=DataSourceKind.synthetic,
            is_synthetic=True,
            description=(
                f"Embedded hardcoded demonstration dataset for {require_city(city_id).name}. "
                "Invented geometries and attributes for end-to-end testing. "
                "Not official flood statistics, census figures, or measured travel times."
            ),
            provider="CRIVAL project (hardcoded demo)",
            license_note="For demonstration and software testing only",
            retrieved_at=datetime.now(timezone.utc),
            provenance={
                "synthetic": True,
                "is_invented": True,
                "source_id": SOURCE_ID,
                "dataset_seed": DATASET_SEED,
                "city_id": city_id,
                "disclaimer": PROVENANCE_NOTE,
                "purpose": "Enable multi-city UI/API testing without external downloads",
            },
        )
        db.add(source)
        db.flush()
    return source, False


def seed_hardcoded_city(
    db: Session, city_id: str, *, force: bool = False
) -> dict[str, Any]:
    city_id = city_id.strip().lower()
    require_city(city_id)
    if city_id not in list_hardcoded_city_ids():
        return {
            "created": False,
            "city_id": city_id,
            "message": f"No hardcoded dataset for city_id={city_id}.",
        }

    source, already = _get_or_create_source(db, city_id, force)
    if already:
        return {
            "created": False,
            "city_id": city_id,
            "data_source_id": str(source.id),
            "message": (
                f"Hardcoded demonstration dataset already present for {city_id}. "
                "Pass force=true to re-insert missing rows."
            ),
        }

    data = build_city_dataset(city_id)
    zone_by_code: dict[str, Zone] = {}

    zones_created = 0
    for zdef in data["zones"]:
        existing = (
            db.query(Zone)
            .filter(Zone.city_id == city_id, Zone.code == zdef["code"])
            .one_or_none()
        )
        if existing:
            zone_by_code[zdef["code"]] = existing
            continue
        geom = ensure_multipolygon(shape(zdef["boundary"]))
        zone = Zone(
            city_id=city_id,
            code=zdef["code"],
            name=zdef["name"],
            description=zdef.get("description"),
            boundary=to_wkb_element(geom),
            properties=zdef["properties"],
            data_source_id=source.id,
        )
        db.add(zone)
        zone_by_code[zdef["code"]] = zone
        zones_created += 1
    db.flush()

    infra_created = 0
    for idef in data["infrastructure"]:
        exists = (
            db.query(Infrastructure)
            .filter(
                Infrastructure.city_id == city_id,
                Infrastructure.external_id == idef["external_id"],
                Infrastructure.data_source_id == source.id,
            )
            .one_or_none()
        )
        if exists:
            continue
        z = zone_by_code.get(idef.get("zone_code") or "")
        line_coords = idef.get("line_coordinates")
        if (
            isinstance(line_coords, list)
            and len(line_coords) >= 2
            and idef.get("infrastructure_type") == "bus_route"
        ):
            from shapely.geometry import LineString

            geom = to_wkb_element(LineString(line_coords))
        else:
            geom = to_wkb_element(Point(idef["lon"], idef["lat"]))
        db.add(
            Infrastructure(
                city_id=city_id,
                name=idef["name"],
                infrastructure_type=InfrastructureType(idef["infrastructure_type"]),
                geometry=geom,
                external_id=idef["external_id"],
                properties=idef["properties"],
                notes=idef.get("notes"),
                zone_id=z.id if z is not None else None,
                data_source_id=source.id,
            )
        )
        infra_created += 1

    hazards_created = 0
    for hdef in data["hazards"]:
        exists = (
            db.query(HazardObservation)
            .filter(
                HazardObservation.city_id == city_id,
                HazardObservation.external_id == hdef["external_id"],
                HazardObservation.data_source_id == source.id,
            )
            .one_or_none()
        )
        if exists:
            continue
        z = zone_by_code.get(hdef.get("zone_code") or "")
        observed = None
        if hdef.get("observed_on"):
            observed = date.fromisoformat(hdef["observed_on"])
        db.add(
            HazardObservation(
                city_id=city_id,
                hazard_type=HazardType(hdef["hazard_type"]),
                severity=SeverityLevel(hdef["severity"]),
                observed_on=observed,
                description=hdef.get("description"),
                severity_score=hdef.get("severity_score"),
                geometry=to_wkb_element(Point(hdef["lon"], hdef["lat"])),
                properties=hdef["properties"],
                external_id=hdef["external_id"],
                zone_id=z.id if z is not None else None,
                data_source_id=source.id,
            )
        )
        hazards_created += 1

    deps_created = 0
    for ddef in data["dependencies"]:
        exists = (
            db.query(DependencyEdge)
            .filter(
                DependencyEdge.source_node == ddef["source_node"],
                DependencyEdge.target_node == ddef["target_node"],
                DependencyEdge.relationship_type == ddef["relationship_type"],
            )
            .one_or_none()
        )
        if exists:
            continue
        z = zone_by_code.get(ddef.get("zone_code") or "") if ddef.get("zone_code") else None
        db.add(
            DependencyEdge(
                source_node=ddef["source_node"],
                target_node=ddef["target_node"],
                relationship_type=ddef["relationship_type"],
                evidence=ddef.get("evidence"),
                evidence_kind=EdgeEvidenceKind(ddef.get("evidence_kind", "hypothesized")),
                strength=ddef.get("strength"),
                confidence=ddef.get("confidence"),
                provenance=ddef.get("provenance") or {},
                zone_id=z.id if z is not None else None,
            )
        )
        deps_created += 1

    reports_created = 0
    for rdef in data["community_reports"]:
        exists = (
            db.query(CommunityReport)
            .filter(
                CommunityReport.city_id == city_id,
                CommunityReport.text_hash == rdef["text_hash"],
            )
            .one_or_none()
        )
        if exists:
            continue
        observed_at = None
        if rdef.get("observed_at"):
            observed_at = datetime.fromisoformat(rdef["observed_at"])
        db.add(
            CommunityReport(
                city_id=city_id,
                text_redacted=rdef["text_redacted"],
                text_hash=rdef["text_hash"],
                near_duplicate_key=rdef.get("near_duplicate_key"),
                disaster_related=rdef.get("disaster_related"),
                disaster_related_proba=rdef.get("disaster_related_proba"),
                labels=rdef.get("labels") or [],
                label_probas=rdef.get("label_probas") or {},
                category=rdef.get("category") or "unclassified",
                needs_human_review=bool(rdef.get("needs_human_review", True)),
                reviewed=bool(rdef.get("reviewed", False)),
                verification_status=rdef.get("verification_status") or "unverified",
                location_precision=rdef.get("location_precision") or "unknown",
                location=rdef.get("location") or {},
                observation_kind=rdef.get("observation_kind") or "simulated",
                source_reliability=rdef.get("source_reliability") or "demo_hardcoded",
                observed_at=observed_at,
                provenance=rdef.get("provenance") or {},
            )
        )
        reports_created += 1

    db.flush()
    return {
        "created": True,
        "city_id": city_id,
        "data_source_id": str(source.id),
        "source_id": SOURCE_ID,
        "dataset_seed": DATASET_SEED,
        "zones": zones_created,
        "infrastructure": infra_created,
        "hazards": hazards_created,
        "dependencies": deps_created,
        "community_reports": reports_created,
        "message": (
            f"Hardcoded demonstration dataset loaded for {city_id}. "
            "All records are invented/simulated (is_synthetic=true)."
        ),
    }


def seed_hardcoded_dataset(
    db: Session,
    *,
    city_id: Optional[str] = None,
    all_cities: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """
    Seed one city or all hardcoded cities.

    - city_id set → that city only
    - all_cities=True → every city in the hardcoded set
    - neither → defaults to all cities (so the app works without manual city picks)
    """
    if city_id and not all_cities:
        return seed_hardcoded_city(db, city_id, force=force)

    results = []
    for cid in list_hardcoded_city_ids():
        results.append(seed_hardcoded_city(db, cid, force=force))
    total_zones = sum(int(r.get("zones") or 0) for r in results)
    created_any = any(r.get("created") for r in results)
    return {
        "created": created_any,
        "all_cities": True,
        "cities": results,
        "zones_inserted": total_zones,
        "message": (
            f"Hardcoded seed across {len(results)} cities "
            f"({total_zones} new zones this run)."
        ),
    }

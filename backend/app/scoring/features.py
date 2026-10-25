"""Extract zone features for scoring using PostGIS spatial queries."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.models.data_source import DataSource
from app.models.hazard import HazardObservation, SeverityLevel
from app.models.infrastructure import Infrastructure, InfrastructureType
from app.models.zone import Zone

SEVERITY_WEIGHTS = {
    SeverityLevel.low: 1.0,
    SeverityLevel.moderate: 2.5,
    SeverityLevel.high: 5.0,
    SeverityLevel.severe: 8.0,
    SeverityLevel.unknown: 1.5,
}


def extract_zone_features(db: Session, zone: Zone) -> dict[str, Any]:
    """Build a feature dict for one zone. Never invents population figures."""
    # Ensure data_source loaded
    if zone.data_source is None:
        zone = (
            db.query(Zone)
            .options(joinedload(Zone.data_source))
            .filter(Zone.id == zone.id)
            .one()
        )

    features: dict[str, Any] = {
        "zone_id": str(zone.id),
        "city_id": zone.city_id,
        "zone_code": zone.code,
        "zone_name": zone.name,
        "zone_is_synthetic": bool(zone.data_source and zone.data_source.is_synthetic),
    }

    _flood_features(db, zone, features)
    _population_features(zone, features)
    _road_and_facility_features(db, zone, features)
    _healthcare_distance(db, zone, features)
    return features


def extract_all_zone_features(
    db: Session,
    zone_ids: Optional[list[UUID]] = None,
    *,
    city_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    q = db.query(Zone).options(joinedload(Zone.data_source))
    if city_id is not None:
        q = q.filter(Zone.city_id == city_id)
    if zone_ids:
        q = q.filter(Zone.id.in_(zone_ids))
    zones = q.order_by(Zone.code).all()
    # Enforce: requested zone_ids must belong to city when both provided
    if city_id is not None and zone_ids:
        found = {z.id for z in zones}
        missing = [zid for zid in zone_ids if zid not in found]
        if missing:
            raise ValueError(
                f"Zone(s) not found for city_id={city_id}: {[str(m) for m in missing]}"
            )
    return [extract_zone_features(db, z) for z in zones]


def _flood_features(db: Session, zone: Zone, features: dict[str, Any]) -> None:
    # Hazards whose geometry intersects the zone boundary
    rows = (
        db.query(HazardObservation, DataSource)
        .join(DataSource, HazardObservation.data_source_id == DataSource.id)
        .filter(
            HazardObservation.city_id == zone.city_id,
            HazardObservation.geometry.isnot(None),
            text(
                "ST_Intersects(hazard_observations.geometry, "
                "(SELECT boundary FROM zones WHERE id = :zid))"
            ),
        )
        .params(zid=str(zone.id))
        .all()
    )
    if not rows:
        features.update(
            {
                "flood_severity_score": None,
                "flood_status": "unavailable",
                "flood_is_synthetic": False,
                "flood_sources": [],
                "flood_notes": "No flood/hazard observations intersect this zone.",
                "flood_observation_count": 0,
            }
        )
        return

    score = 0.0
    sources: list[str] = []
    any_synth = False
    for haz, src in rows:
        score += SEVERITY_WEIGHTS.get(haz.severity, 1.5)
        sources.append(src.name)
        if src.is_synthetic:
            any_synth = True

    features.update(
        {
            "flood_severity_score": round(score, 4),
            "flood_status": "synthetic" if any_synth else "available",
            "flood_is_synthetic": any_synth,
            "flood_sources": sorted(set(sources)),
            "flood_notes": f"{len(rows)} intersecting hazard observation(s).",
            "flood_observation_count": len(rows),
        }
    )


def _population_features(zone: Zone, features: dict[str, Any]) -> None:
    props = zone.properties or {}
    # Only accept explicitly provided population keys — never invent
    pop = props.get("population")
    if pop is None:
        pop = props.get("population_estimate")
    if pop is None:
        features.update(
            {
                "population": None,
                "population_is_synthetic": False,
                "population_sources": [],
                "population_notes": (
                    "No population or population_estimate property on zone."
                ),
            }
        )
        return
    try:
        pop_f = float(pop)
    except (TypeError, ValueError):
        features.update(
            {
                "population": None,
                "population_is_synthetic": False,
                "population_sources": [],
                "population_notes": "Population property present but not numeric.",
            }
        )
        return
    is_synth = bool(props.get("population_is_synthetic")) or bool(
        zone.data_source and zone.data_source.is_synthetic and "population" in props
    )
    # If synthetic zone invented population without flag, still require explicit key —
    # we only mark synthetic when flagged or when property says so.
    features.update(
        {
            "population": pop_f,
            "population_is_synthetic": is_synth,
            "population_sources": [
                zone.data_source.name if zone.data_source else "zone.properties"
            ],
            "population_notes": (
                "Population from zone properties — verify provenance before "
                "treating as official census."
            ),
        }
    )


def _road_and_facility_features(
    db: Session, zone: Zone, features: dict[str, Any]
) -> None:
    infra_rows = (
        db.query(Infrastructure, DataSource)
        .join(DataSource, Infrastructure.data_source_id == DataSource.id)
        .filter(
            Infrastructure.city_id == zone.city_id,
            text(
                "ST_Intersects(infrastructure.geometry, "
                "(SELECT boundary FROM zones WHERE id = :zid))"
            ),
        )
        .params(zid=str(zone.id))
        .all()
    )

    roads = [
        (i, s)
        for i, s in infra_rows
        if i.infrastructure_type == InfrastructureType.road
    ]
    facilities = [
        (i, s)
        for i, s in infra_rows
        if i.infrastructure_type
        in {
            InfrastructureType.hospital,
            InfrastructureType.clinic,
            InfrastructureType.emergency_facility,
        }
    ]

    # Flood near roads inside/near zone (buffer ~200m ≈ 0.002 deg rough)
    flood_near_roads = db.execute(
        text(
            """
            SELECT COUNT(*) FROM hazard_observations h
            WHERE h.geometry IS NOT NULL
              AND h.city_id = :cid
              AND EXISTS (
                SELECT 1 FROM infrastructure i
                WHERE i.infrastructure_type = 'road'
                  AND i.city_id = :cid
                  AND ST_DWithin(h.geometry::geography, i.geometry::geography, 200)
              )
              AND ST_Intersects(
                    h.geometry,
                    (SELECT boundary FROM zones WHERE id = :zid)
                  )
            """
        ),
        {"zid": str(zone.id), "cid": zone.city_id},
    ).scalar()
    flood_near = int(flood_near_roads or 0)

    if not roads and flood_near == 0 and not facilities:
        # Still can compute disruption proxy from flood alone if floods exist
        pass

    # Disruption index: floods near roads + penalty for zero roads when floods exist
    flood_score = float(features.get("flood_severity_score") or 0)
    road_count = len(roads)
    if road_count == 0 and flood_near == 0 and flood_score == 0:
        features.update(
            {
                "road_disruption_index": None,
                "road_status": "unavailable",
                "road_is_synthetic": False,
                "road_sources": [],
                "road_notes": "No road infrastructure or flood–road co-location signals.",
                "road_count": 0,
            }
        )
    else:
        # Higher when floods near roads; slight increase when roads are scarce
        scarcity = 2.0 if road_count == 0 else max(0.0, 1.5 - 0.3 * road_count)
        index = flood_near * 2.0 + scarcity + min(flood_score, 5.0) * 0.3
        any_synth = any(s.is_synthetic for _, s in roads) or bool(
            features.get("flood_is_synthetic")
        )
        sources = sorted({s.name for _, s in roads} | set(features.get("flood_sources") or []))
        features.update(
            {
                "road_disruption_index": round(index, 4),
                "road_status": "synthetic" if any_synth else "available",
                "road_is_synthetic": any_synth,
                "road_sources": sources,
                "road_notes": (
                    f"{road_count} road feature(s) in zone; "
                    f"{flood_near} hazard(s) within ~200m of a road."
                ),
                "road_count": road_count,
            }
        )

    if facilities:
        any_synth_f = any(s.is_synthetic for _, s in facilities)
        features.update(
            {
                "facility_count": len(facilities),
                "facility_status": "synthetic" if any_synth_f else "available",
                "facility_is_synthetic": any_synth_f,
                "facility_sources": sorted({s.name for _, s in facilities}),
                "facility_notes": f"{len(facilities)} emergency-relevant facilit(y/ies) in zone.",
            }
        )
    else:
        # Zero facilities is informative (available raw=0), not unavailable
        features.update(
            {
                "facility_count": 0,
                "facility_status": "available",
                "facility_is_synthetic": False,
                "facility_sources": [],
                "facility_notes": "No hospital/clinic/emergency facilities intersect zone.",
            }
        )


def _healthcare_distance(db: Session, zone: Zone, features: dict[str, Any]) -> None:
    row = db.execute(
        text(
            """
            SELECT
              ST_Distance(
                (SELECT ST_Centroid(boundary)::geography FROM zones WHERE id = :zid),
                i.geometry::geography
              ) / 1000.0 AS dist_km,
              i.name,
              ds.name AS source_name,
              ds.is_synthetic
            FROM infrastructure i
            JOIN data_sources ds ON ds.id = i.data_source_id
            WHERE i.city_id = :cid
              AND i.infrastructure_type IN
              ('hospital', 'clinic', 'emergency_facility')
            ORDER BY dist_km ASC
            LIMIT 1
            """
        ),
        {"zid": str(zone.id), "cid": zone.city_id},
    ).mappings().first()

    if not row:
        features.update(
            {
                "nearest_healthcare_km": None,
                "healthcare_status": "unavailable",
                "healthcare_is_synthetic": False,
                "healthcare_sources": [],
                "healthcare_notes": (
                    "No hospital/clinic/emergency facilities in the database."
                ),
            }
        )
        return

    features.update(
        {
            "nearest_healthcare_km": round(float(row["dist_km"]), 4),
            "healthcare_status": "synthetic" if row["is_synthetic"] else "available",
            "healthcare_is_synthetic": bool(row["is_synthetic"]),
            "healthcare_sources": [row["source_name"]],
            "healthcare_notes": (
                f"Nearest facility '{row['name']}' at ~{float(row['dist_km']):.2f} km "
                "great-circle distance (not network travel time)."
            ),
            "nearest_healthcare_name": row["name"],
        }
    )

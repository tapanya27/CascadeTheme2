"""Overview stats and map GeoJSON from PostgreSQL/PostGIS."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.models.assessment import VulnerabilityAssessment
from app.models.community_report import CommunityReport
from app.models.data_source import DataSource
from app.models.hazard import HazardObservation
from app.models.infrastructure import Infrastructure
from app.models.zone import Zone
from app.nlp.reports import enrich_empty_labels_from_keywords
from app.repositories.assessments import AssessmentRepository
from app.schemas.dashboard import (
    CategoryCount,
    DataFreshness,
    HealthcareSummary,
    HighPriorityZone,
    MapFeatureCollection,
    MapLayersResponse,
    OverviewResponse,
    ZoneContextItem,
    ZoneContextResponse,
)

CATEGORY_LABELS = {
    "low": "Low",
    "moderate": "Moderate",
    "high": "High",
    "critical": "Critical",
}


class DashboardService:
    def __init__(self, db: Session):
        self.db = db
        self.assessments = AssessmentRepository(db)

    def overview(self, *, city_id: str) -> OverviewResponse:
        zones = (
            self.db.query(Zone)
            .options(joinedload(Zone.data_source))
            .filter(Zone.city_id == city_id)
            .order_by(Zone.code)
            .all()
        )
        latest_rows = self.assessments.latest_batch(city_id=city_id)
        by_zone = {r.zone_id: r for r in latest_rows}

        category_counter: Counter[str] = Counter()
        for z in zones:
            a = by_zone.get(z.id)
            if a and a.category:
                category_counter[a.category] += 1

        category_counts = [
            CategoryCount(
                category=key,
                count=category_counter.get(key, 0),
                label=CATEGORY_LABELS.get(key, key.title()),
            )
            for key in ("low", "moderate", "high", "critical")
        ]

        high_priority: list[HighPriorityZone] = []
        for a in sorted(
            [r for r in latest_rows if r.overall_score is not None],
            key=lambda r: r.overall_score or 0,
            reverse=True,
        ):
            if a.category not in {"high", "critical"} and (
                a.overall_score is None or a.overall_score < 50
            ):
                continue
            z = a.zone
            if not z or z.city_id != city_id:
                continue
            high_priority.append(
                HighPriorityZone(
                    zone_id=z.id,
                    code=z.code,
                    name=z.name,
                    overall_score=a.overall_score,
                    category=a.category,
                    is_synthetic=z.data_source.is_synthetic if z.data_source else None,
                    confidence=a.confidence,
                    hazard_only_score=getattr(a, "hazard_only_score", None),
                    hazard_only_rank=getattr(a, "hazard_only_rank", None),
                    multifactor_rank=getattr(a, "multifactor_rank", None),
                    rank_uplift=getattr(a, "rank_uplift", None),
                )
            )
            if len(high_priority) >= 5:
                break

        travel_values: list[float] = []
        for a in latest_rows:
            inputs = a.inputs or {}
            km = inputs.get("nearest_healthcare_km")
            if km is not None:
                try:
                    travel_values.append(float(km))
                except (TypeError, ValueError):
                    pass

        sources = (
            self.db.query(DataSource).filter(DataSource.city_id == city_id).all()
        )
        synth = sum(1 for s in sources if s.is_synthetic)
        authentic = len(sources) - synth

        findings: list[str] = []
        if not zones:
            findings.append(
                f"No zones loaded for city_id={city_id}. "
                "Import OSM/GeoJSON or seed synthetic data for this city only — "
                "records from other cities are never reused."
            )
        elif not latest_rows:
            findings.append(
                "No assessments yet for this city. Run POST /api/assessments/run "
                f"with city_id={city_id} (or use Zone details)."
            )
        else:
            findings.append(
                f"{len(latest_rows)} of {len(zones)} zones have scores in the latest run "
                f"({latest_rows[0].scoring_version})."
            )
            crit = category_counter.get("critical", 0) + category_counter.get("high", 0)
            if crit:
                findings.append(
                    f"{crit} zone(s) currently classify as high or critical under this model."
                )
            if travel_values:
                findings.append(
                    f"Mean nearest-facility great-circle distance among assessed zones "
                    f"with travel data: {sum(travel_values)/len(travel_values):.2f} km "
                    "(not measured travel time)."
                )
            if synth:
                findings.append(
                    f"{synth} data source(s) are synthetic demonstration feeds — "
                    "visually labelled and not verified measurements."
                )

        return OverviewResponse(
            city_id=city_id,
            total_zones=len(zones),
            zones_assessed=len(latest_rows),
            category_counts=category_counts,
            high_priority=high_priority,
            healthcare=HealthcareSummary(
                zones_with_travel_burden=len(travel_values),
                average_nearest_healthcare_km=(
                    round(sum(travel_values) / len(travel_values), 3)
                    if travel_values
                    else None
                ),
                note=(
                    "Distances are geometric approximations from assessment inputs, "
                    "not ambulance ETAs."
                ),
            ),
            freshness=DataFreshness(
                latest_assessment_at=latest_rows[0].created_at if latest_rows else None,
                latest_run_id=latest_rows[0].run_id if latest_rows else None,
                scoring_version=latest_rows[0].scoring_version if latest_rows else None,
                data_source_count=len(sources),
                synthetic_source_count=synth,
                authentic_source_count=authentic,
            ),
            key_findings=findings,
            map_preview_zone_ids=[z.id for z in zones[:8]],
            disclaimer=(
                f"Dashboard figures for city_id={city_id} only. "
                "Scores are transparent composites — not validated predictions. "
                "Empty layers mean this city has no imported data (not another city's data)."
            ),
        )

    def map_layers(self, *, city_id: str) -> MapLayersResponse:
        zones = (
            self.db.query(Zone)
            .options(joinedload(Zone.data_source))
            .filter(Zone.city_id == city_id)
            .order_by(Zone.code)
            .all()
        )
        latest = {
            r.zone_id: r for r in self.assessments.latest_batch(city_id=city_id)
        }

        zone_features: list[dict[str, Any]] = []
        for z in zones:
            geom = _to_geojson(z.boundary)
            if not geom:
                continue
            a = latest.get(z.id)
            top_factors: list[str] = []
            if a and a.components:
                scored = [
                    c
                    for c in a.components
                    if isinstance(c, dict) and c.get("contribution") is not None
                ]
                scored.sort(key=lambda c: float(c.get("contribution") or 0), reverse=True)
                top_factors = [str(c.get("label") or c.get("key")) for c in scored[:3]]
            zone_features.append(
                {
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {
                        "id": str(z.id),
                        "city_id": z.city_id,
                        "code": z.code,
                        "name": z.name,
                        "is_synthetic": bool(
                            z.data_source.is_synthetic if z.data_source else False
                        ),
                        "data_source": z.data_source.name if z.data_source else None,
                        "overall_score": a.overall_score if a else None,
                        "category": a.category if a else None,
                        "confidence": a.confidence if a else None,
                        "data_quality": a.data_quality if a else {},
                        "top_factors": top_factors,
                        "scoring_version": a.scoring_version if a else None,
                    },
                }
            )

        hazards = (
            self.db.query(HazardObservation)
            .options(joinedload(HazardObservation.data_source))
            .filter(HazardObservation.city_id == city_id)
            .all()
        )
        hazard_features = []
        for h in hazards:
            geom = _to_geojson(h.geometry)
            if not geom:
                continue
            hazard_features.append(
                {
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {
                        "id": str(h.id),
                        "city_id": h.city_id,
                        "kind": h.hazard_type.value,
                        "severity": h.severity.value,
                        "is_synthetic": bool(
                            h.data_source.is_synthetic if h.data_source else False
                        ),
                        "data_source": h.data_source.name if h.data_source else None,
                        "description": h.description,
                    },
                }
            )

        infra = (
            self.db.query(Infrastructure)
            .options(joinedload(Infrastructure.data_source))
            .filter(Infrastructure.city_id == city_id)
            .all()
        )
        infra_features = []
        for i in infra:
            geom = _to_geojson(i.geometry)
            if not geom:
                continue
            infra_features.append(
                {
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {
                        "id": str(i.id),
                        "city_id": i.city_id,
                        "name": i.name,
                        "kind": i.infrastructure_type.value,
                        "is_synthetic": bool(
                            i.data_source.is_synthetic if i.data_source else False
                        ),
                        "data_source": i.data_source.name if i.data_source else None,
                    },
                }
            )

        # Community reports with explicit coordinates only — no guessed locations.
        report_rows = (
            self.db.query(CommunityReport)
            .filter(
                CommunityReport.city_id == city_id,
                CommunityReport.location_precision == "coordinates",
            )
            .order_by(CommunityReport.created_at.desc())
            .limit(500)
            .all()
        )
        report_features: list[dict[str, Any]] = []
        for r in report_rows:
            loc = r.location or {}
            lon = loc.get("lon")
            lat = loc.get("lat")
            if lon is None or lat is None:
                continue
            try:
                lon_f, lat_f = float(lon), float(lat)
            except (TypeError, ValueError):
                continue
            labels, category, used_kw = enrich_empty_labels_from_keywords(
                r.text_redacted or "",
                labels=list(r.labels or []),
                disaster_related=r.disaster_related,
            )
            # Persist enrichment so Recent reports and map stay consistent
            if used_kw and (
                not r.labels
                or getattr(r, "category", None) in (None, "", "unclassified")
            ):
                r.labels = labels
                r.category = category
            excerpt = (r.text_redacted or "").strip()
            if len(excerpt) > 100:
                excerpt = excerpt[:97] + "…"
            report_features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon_f, lat_f],
                    },
                    "properties": {
                        "id": str(r.id),
                        "layer": "community_report",
                        "city_id": r.city_id,
                        "category": category,
                        "labels": labels,
                        "verification_status": getattr(
                            r, "verification_status", None
                        )
                        or "unverified",
                        "needs_human_review": r.needs_human_review,
                        "created_at": r.created_at.isoformat()
                        if r.created_at
                        else None,
                        "observation_kind": r.observation_kind,
                        "marker_kind": "community_report",
                        "text_excerpt": excerpt,
                    },
                }
            )

        notes = [
            f"Layers scoped to city_id={city_id} only.",
            "Zone polygons and points come from PostGIS geometries.",
            "Synthetic features are flagged is_synthetic=true in properties.",
            "Community reports appear only when the submitter provided lon/lat.",
            "Empty layers mean no data for this city — not a fallback to another city.",
            "Tiles: use OSM attribution in the frontend map.",
        ]
        return MapLayersResponse(
            city_id=city_id,
            zones=MapFeatureCollection(
                features=zone_features,
                meta={"count": len(zone_features), "layer": "zones", "city_id": city_id},
            ),
            hazards=MapFeatureCollection(
                features=hazard_features,
                meta={"count": len(hazard_features), "layer": "hazards", "city_id": city_id},
            ),
            infrastructure=MapFeatureCollection(
                features=infra_features,
                meta={
                    "count": len(infra_features),
                    "layer": "infrastructure",
                    "city_id": city_id,
                },
            ),
            community_reports=MapFeatureCollection(
                features=report_features,
                meta={
                    "count": len(report_features),
                    "layer": "community_reports",
                    "city_id": city_id,
                },
            ),
            generated_at=datetime.now(timezone.utc),
            notes=notes,
        )

    def zone_context(
        self, zone_id: UUID, *, city_id: Optional[str] = None
    ) -> Optional[ZoneContextResponse]:
        q = (
            self.db.query(Zone)
            .options(joinedload(Zone.data_source))
            .filter(Zone.id == zone_id)
        )
        if city_id is not None:
            q = q.filter(Zone.city_id == city_id)
        zone = q.one_or_none()
        if not zone:
            return None

        haz_rows = (
            self.db.query(HazardObservation)
            .options(joinedload(HazardObservation.data_source))
            .filter(
                HazardObservation.city_id == zone.city_id,
                HazardObservation.geometry.isnot(None),
                text(
                    "ST_Intersects(hazard_observations.geometry, "
                    "(SELECT boundary FROM zones WHERE id = :zid))"
                ),
            )
            .params(zid=str(zone_id))
            .all()
        )
        infra_rows = (
            self.db.query(Infrastructure)
            .options(joinedload(Infrastructure.data_source))
            .filter(
                Infrastructure.city_id == zone.city_id,
                text(
                    "ST_Intersects(infrastructure.geometry, "
                    "(SELECT boundary FROM zones WHERE id = :zid))"
                ),
            )
            .params(zid=str(zone_id))
            .all()
        )

        return ZoneContextResponse(
            zone_id=zone.id,
            city_id=zone.city_id,
            zone_code=zone.code,
            zone_name=zone.name,
            is_synthetic=zone.data_source.is_synthetic if zone.data_source else None,
            hazards=[
                ZoneContextItem(
                    id=h.id,
                    name=h.description or h.hazard_type.value,
                    kind=h.hazard_type.value,
                    is_synthetic=bool(
                        h.data_source.is_synthetic if h.data_source else False
                    ),
                    data_source_name=h.data_source.name if h.data_source else None,
                    properties=h.properties or {},
                    geometry=_to_geojson(h.geometry),
                    extra={"severity": h.severity.value, "observed_on": str(h.observed_on)},
                )
                for h in haz_rows
            ],
            infrastructure=[
                ZoneContextItem(
                    id=i.id,
                    name=i.name,
                    kind=i.infrastructure_type.value,
                    is_synthetic=bool(
                        i.data_source.is_synthetic if i.data_source else False
                    ),
                    data_source_name=i.data_source.name if i.data_source else None,
                    properties=i.properties or {},
                    geometry=_to_geojson(i.geometry),
                    extra={},
                )
                for i in infra_rows
            ],
            note=(
                "Context lists PostGIS-intersecting hazards and infrastructure. "
                "Synthetic rows are labelled."
            ),
        )


def _to_geojson(db_geom: Any) -> Optional[dict[str, Any]]:
    if db_geom is None:
        return None
    try:
        return mapping(to_shape(db_geom))
    except Exception:  # noqa: BLE001
        return None

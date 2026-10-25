"""Data source and export repository."""

from __future__ import annotations

from datetime import datetime, timezone

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy.orm import Session

from app.models.data_source import DataSource
from app.models.hazard import HazardObservation
from app.models.infrastructure import Infrastructure
from app.models.zone import Zone
from app.schemas.data import DataSourceOut, ExportResponse


class DataSourceRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self, *, city_id: str) -> list[DataSourceOut]:
        rows = (
            self.db.query(DataSource)
            .filter(DataSource.city_id == city_id)
            .order_by(DataSource.created_at.desc())
            .all()
        )
        return [DataSourceOut.model_validate(r) for r in rows]

    def export_all(self, *, city_id: str) -> ExportResponse:
        sources = (
            self.db.query(DataSource).filter(DataSource.city_id == city_id).all()
        )
        zones = self.db.query(Zone).filter(Zone.city_id == city_id).all()
        infra = (
            self.db.query(Infrastructure)
            .filter(Infrastructure.city_id == city_id)
            .all()
        )
        hazards = (
            self.db.query(HazardObservation)
            .filter(HazardObservation.city_id == city_id)
            .all()
        )

        source_map = {s.id: s for s in sources}

        def geom_json(g):
            if g is None:
                return None
            try:
                return mapping(to_shape(g))
            except Exception:  # noqa: BLE001
                return None

        return ExportResponse(
            format="json",
            generated_at=datetime.now(timezone.utc),
            data_sources=[
                {
                    "id": str(s.id),
                    "city_id": s.city_id,
                    "name": s.name,
                    "kind": s.kind.value,
                    "is_synthetic": s.is_synthetic,
                    "provenance": s.provenance,
                }
                for s in sources
            ],
            zones=[
                {
                    "id": str(z.id),
                    "city_id": z.city_id,
                    "code": z.code,
                    "name": z.name,
                    "is_synthetic": source_map[z.data_source_id].is_synthetic
                    if z.data_source_id in source_map
                    else None,
                    "data_source": source_map[z.data_source_id].name
                    if z.data_source_id in source_map
                    else None,
                    "geometry": geom_json(z.boundary),
                    "properties": z.properties,
                }
                for z in zones
            ],
            infrastructure=[
                {
                    "id": str(i.id),
                    "city_id": i.city_id,
                    "name": i.name,
                    "type": i.infrastructure_type.value,
                    "is_synthetic": source_map[i.data_source_id].is_synthetic
                    if i.data_source_id in source_map
                    else None,
                    "data_source": source_map[i.data_source_id].name
                    if i.data_source_id in source_map
                    else None,
                    "geometry": geom_json(i.geometry),
                    "properties": i.properties,
                }
                for i in infra
            ],
            hazards=[
                {
                    "id": str(h.id),
                    "city_id": h.city_id,
                    "hazard_type": h.hazard_type.value,
                    "severity": h.severity.value,
                    "observed_on": h.observed_on.isoformat() if h.observed_on else None,
                    "is_synthetic": source_map[h.data_source_id].is_synthetic
                    if h.data_source_id in source_map
                    else None,
                    "data_source": source_map[h.data_source_id].name
                    if h.data_source_id in source_map
                    else None,
                    "geometry": geom_json(h.geometry),
                    "description": h.description,
                }
                for h in hazards
            ],
        )

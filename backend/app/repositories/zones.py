"""Zone repository."""

from __future__ import annotations

import math
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.geospatial.geometry import geometry_to_geojson
from app.models.zone import Zone
from app.schemas.zone import ZoneOut


class ZoneRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_zones(
        self,
        page: int = 1,
        page_size: int = 20,
        *,
        city_id: str,
    ) -> tuple[list[ZoneOut], int]:
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        q = (
            self.db.query(Zone)
            .options(joinedload(Zone.data_source))
            .filter(Zone.city_id == city_id)
        )
        total = q.count()
        rows = (
            q.order_by(Zone.code)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        items = [self._to_out(z) for z in rows]
        return items, total

    def get(
        self, zone_id: UUID, *, city_id: Optional[str] = None
    ) -> Optional[ZoneOut]:
        q = (
            self.db.query(Zone)
            .options(joinedload(Zone.data_source))
            .filter(Zone.id == zone_id)
        )
        if city_id is not None:
            q = q.filter(Zone.city_id == city_id)
        z = q.one_or_none()
        return self._to_out(z) if z else None

    @staticmethod
    def pages(total: int, page_size: int) -> int:
        return max(1, math.ceil(total / page_size)) if total else 0

    def _to_out(self, z: Zone) -> ZoneOut:
        return ZoneOut(
            id=z.id,
            city_id=z.city_id,
            code=z.code,
            name=z.name,
            description=z.description,
            properties=z.properties or {},
            data_source_id=z.data_source_id,
            data_source_name=z.data_source.name if z.data_source else None,
            is_synthetic=z.data_source.is_synthetic if z.data_source else None,
            geojson=geometry_to_geojson(z.boundary),
            created_at=z.created_at,
            updated_at=z.updated_at,
        )

"""Dataset ingestion endpoints (weather, flood labels, report corpora)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.cities.registry import require_city, resolve_bbox
from app.config import get_settings
from app.database import get_db
from app.ingestion.base import DataLake
from app.ingestion.cds_era5 import CdsEra5Provider
from app.ingestion.disaster_reports import DisasterResponseMessagesProvider
from app.ingestion.flood_events import ExternalFloodEventsProvider, FloodEventProxyProvider
from app.ingestion.open_meteo import OpenMeteoPrecipitationProvider, default_train_window
from app.security import check_rate_limit

router = APIRouter(tags=["ingest"])


def _lake() -> DataLake:
    return DataLake(Path(get_settings().data_dir))


class OpenMeteoRequest(BaseModel):
    city_id: str = "nagpur"
    start: Optional[date] = None
    end: Optional[date] = None
    force: bool = False
    include_soil_moisture: bool = False


class Era5Request(BaseModel):
    city_id: str = "nagpur"
    year: int = 2023
    month: int = 7
    day: Optional[int] = None
    variables: list[str] = Field(default_factory=lambda: ["total_precipitation"])


class FloodProxyRequest(BaseModel):
    city_id: str = "nagpur"
    features_parquet: Optional[str] = None
    rain_24h_threshold_mm: float = 80.0
    rain_72h_threshold_mm: float = 150.0
    horizon_hours: int = 24


@router.post("/api/ingest/weather/open-meteo")
def ingest_open_meteo(body: OpenMeteoRequest, request: Request):
    check_rate_limit(request, expensive=True)
    try:
        city = require_city(body.city_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    start, end = body.start, body.end
    if start is None or end is None:
        start, end = default_train_window()
    result = OpenMeteoPrecipitationProvider(_lake()).ingest(
        lon=city.centroid[0],
        lat=city.centroid[1],
        start=start,
        end=end,
        city_id=city.id,
        force=body.force,
        include_soil_moisture=body.include_soil_moisture,
    )
    return result.to_dict()


@router.post("/api/ingest/weather/era5")
def ingest_era5(body: Era5Request, request: Request):
    check_rate_limit(request, expensive=True)
    try:
        bbox, _city = resolve_bbox(city_id=body.city_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    w, s, e, n = bbox
    result = CdsEra5Provider(_lake()).ingest(
        west=w,
        south=s,
        east=e,
        north=n,
        year=body.year,
        month=body.month,
        day=body.day,
        variables=body.variables,
    )
    return result.to_dict()


@router.post("/api/ingest/flood-labels/proxy")
def ingest_flood_proxy(body: FloodProxyRequest, request: Request):
    check_rate_limit(request, expensive=True)
    features_path = body.features_parquet
    if not features_path:
        # Pick latest features for city from open_meteo processed dir
        proc = _lake().provider_processed("open_meteo_archive")
        candidates = sorted(
            proc.glob(f"{body.city_id}_*_features.parquet"),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            raise HTTPException(
                status_code=400,
                detail="No Open-Meteo features found. Run /api/ingest/weather/open-meteo first.",
            )
        features_path = str(candidates[-1])
    try:
        result = FloodEventProxyProvider(_lake()).ingest(
            features_parquet=features_path,
            rain_24h_threshold_mm=body.rain_24h_threshold_mm,
            rain_72h_threshold_mm=body.rain_72h_threshold_mm,
            horizon_hours=body.horizon_hours,
            city_id=body.city_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Flood label build failed: {type(exc).__name__}",
        ) from exc
    return result.to_dict()


@router.post("/api/ingest/flood-labels/external")
def ingest_flood_external(
    request: Request,
    path: str = Query(..., description="Path to CSV/GeoJSON event file"),
    city_id: Optional[str] = None,
):
    check_rate_limit(request, expensive=True)
    return ExternalFloodEventsProvider(_lake()).ingest(path=path, city_id=city_id).to_dict()


@router.post("/api/ingest/reports/corpus")
def ingest_report_corpus(request: Request, force: bool = False):
    check_rate_limit(request, expensive=True)
    return DisasterResponseMessagesProvider(_lake()).ingest(force=force).to_dict()


@router.get("/api/ingest/status")
def ingest_status():
    lake = _lake()
    def _count(p: Path) -> int:
        return len(list(p.glob("*"))) if p.exists() else 0

    return {
        "data_dir": str(lake.root.resolve()),
        "raw": {d.name: _count(d) for d in lake.raw.iterdir()} if lake.raw.exists() else {},
        "processed": {
            d.name: _count(d) for d in lake.processed.iterdir()
        }
        if lake.processed.exists()
        else {},
        "models": _count(lake.models),
        "blockers": {
            "cds_era5": "Requires CDSAPI_KEY + accepted dataset terms",
            "gfd_modis": "Requires Google Earth Engine auth",
            "imd_nwdp": "Government portal access/terms",
        },
    }

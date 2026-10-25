"""Data validation, import, export, OSM, and synthetic seed endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.cities.deps import parse_city_id
from app.database import get_db
from app.models.data_source import DataSourceKind
from app.repositories.data_sources import DataSourceRepository
from app.schemas.data import DataSourceOut, ExportResponse, ImportResult, ValidationResult
from app.security import check_rate_limit, read_upload_limited
from app.services.import_service import ImportService
from app.services.osm_importer import OsmImporter
from app.services.synthetic_data import seed_synthetic_dataset

router = APIRouter(tags=["data"])


@router.get("/api/data/sources", response_model=list[DataSourceOut])
def list_sources(
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> list[DataSourceOut]:
    return DataSourceRepository(db).list_all(city_id=city_id)


@router.post("/api/data/validate", response_model=ValidationResult)
async def validate_upload(
    request: Request,
    file: UploadFile = File(...),
    record_type: str = Form(...),
    source_epsg: Optional[int] = Form(None),
    db: Session = Depends(get_db),
) -> ValidationResult:
    check_rate_limit(request, expensive=True)
    _assert_record_type(record_type)
    content, filename = await read_upload_limited(file)
    service = ImportService(db)
    lower = filename.lower()
    if lower.endswith(".csv"):
        result, _ = service.validate_csv(content, record_type, filename)
    elif lower.endswith(".geojson") or lower.endswith(".json"):
        result, _ = service.validate_geojson(
            content, record_type, filename, source_epsg=source_epsg
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload .csv, .geojson, or .json",
        )
    return result


@router.post("/api/data/import", response_model=ImportResult)
async def import_upload(
    request: Request,
    file: UploadFile = File(...),
    record_type: str = Form(...),
    city_id: str = Depends(parse_city_id),
    source_name: Optional[str] = Form(None),
    commit: bool = Form(True),
    source_epsg: Optional[int] = Form(None),
    is_synthetic: bool = Form(False),
    db: Session = Depends(get_db),
) -> ImportResult:
    check_rate_limit(request, expensive=True)
    _assert_record_type(record_type)
    content, filename = await read_upload_limited(file)

    service = ImportService(db)
    lower = filename.lower()

    if lower.endswith(".csv"):
        validation, parsed = service.validate_csv(content, record_type, filename)
        kind = DataSourceKind.csv_import
    elif lower.endswith(".geojson") or lower.endswith(".json"):
        validation, parsed = service.validate_geojson(
            content, record_type, filename, source_epsg=source_epsg
        )
        kind = DataSourceKind.geojson_import
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload .csv, .geojson, or .json",
        )

    name = source_name or f"Import {filename}"
    try:
        result = service.import_records(
            parsed=parsed,
            validation=validation,
            record_type=record_type,
            source_name=name,
            kind=kind,
            commit=commit,
            is_synthetic=is_synthetic,
            city_id=city_id,
            provenance={
                "filename": filename,
                "record_type": record_type,
                "is_synthetic": is_synthetic,
                "city_id": city_id,
                "description": f"User upload of {filename} for city_id={city_id}",
            },
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Import failed. Validation may have passed but persistence did not.",
        )

    if not validation.valid:
        raise HTTPException(status_code=422, detail=result.model_dump(mode="json"))
    return result


@router.get("/api/data/export", response_model=ExportResponse)
def export_data(
    city_id: str = Depends(parse_city_id),
    db: Session = Depends(get_db),
) -> ExportResponse:
    return DataSourceRepository(db).export_all(city_id=city_id)


@router.post("/api/data/osm/import", response_model=ImportResult)
def import_osm(
    request: Request,
    city_id: str = Depends(parse_city_id),
    commit: bool = True,
    west: Optional[float] = None,
    south: Optional[float] = None,
    east: Optional[float] = None,
    north: Optional[float] = None,
    db: Session = Depends(get_db),
) -> ImportResult:
    check_rate_limit(request, expensive=True)
    try:
        return OsmImporter(db).fetch_and_import(
            commit=commit,
            city_id=city_id,
            west=west,
            south=south,
            east=east,
            north=north,
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail="OSM import failed due to an upstream or network error.",
        )


@router.post("/api/data/synthetic/seed")
def seed_synthetic(
    request: Request,
    city_id: str = Depends(parse_city_id),
    force: bool = False,
    all_cities: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    """Load embedded hardcoded demo data (invented). all_cities=true seeds every city."""
    check_rate_limit(request, expensive=True)
    try:
        return seed_synthetic_dataset(
            db, force=force, city_id=city_id, all_cities=all_cities
        )
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Synthetic seed failed.")


def _assert_record_type(record_type: str) -> None:
    if record_type not in {"zones", "infrastructure", "hazards"}:
        raise HTTPException(
            status_code=400,
            detail="record_type must be one of: zones, infrastructure, hazards",
        )

"""Health and metadata endpoints."""

from fastapi import APIRouter

from app import __version__
from app.cities.registry import get_city
from app.config import get_settings
from app.database import check_database_health
from app.schemas.common import HealthResponse, MetadataResponse

router = APIRouter(tags=["system"])


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db_status = check_database_health()
    connected = db_status["database"] == "connected" and db_status["postgis"]
    error = db_status.get("error")
    if error and ("password" in error.lower() or "postgresql+psycopg" in error.lower()):
        error = "Database connection failed"
    return HealthResponse(
        status="ok" if connected else "degraded",
        version=__version__,
        database=db_status["database"],
        postgis=bool(db_status["postgis"]),
        postgis_version=db_status.get("postgis_version"),
        error=error,
    )


@router.get("/api/metadata", response_model=MetadataResponse)
def metadata() -> MetadataResponse:
    settings = get_settings()
    city = get_city(settings.default_city_id)
    study = (
        f"{city.name}, {city.country}"
        if city
        else "City-agnostic (select via /api/cities)"
    )
    return MetadataResponse(
        project="CRIVAL: Hidden Community Vulnerability",
        module="Crises Before Crises — Early Warning + Vulnerability Intelligence",
        study_area=study,
        spatial_srid=settings.spatial_srid,
        endpoints=[
            "GET /api/health",
            "GET /api/metadata",
            "GET /api/cities",
            "GET /api/dashboard/overview",
            "GET /api/map/layers",
            "GET /api/zones",
            "POST /api/assessments/run",
            "GET /api/assessments/latest",
            "POST /api/assessments/sensitivity",
            "POST /api/interventions/compare",
            "GET /api/interventions",
            "GET /api/data/sources",
            "POST /api/data/validate",
            "POST /api/data/import",
            "GET /api/data/export",
            "POST /api/data/osm/import",
            "POST /api/data/synthetic/seed",
            "POST /api/ingest/weather/open-meteo",
            "POST /api/ingest/weather/era5",
            "POST /api/ingest/flood-labels/proxy",
            "POST /api/ingest/reports/corpus",
            "POST /api/early-warning/train",
            "GET /api/early-warning/status",
            "GET /api/early-warning/predict",
            "POST /api/reports/train",
            "POST /api/reports/submit",
            "GET /api/reports",
            "POST /api/cascade/simulate",
            "POST /api/resilience/run",
        ],
        notes=[
            "PostgreSQL with PostGIS is mandatory; SQLite is not supported.",
            "City-agnostic: pass city_id or custom bbox; default city is configurable.",
            "Synthetic demonstration records are labelled is_synthetic=true.",
            "Forecast likelihood, vulnerability ranking, and confidence are separate concepts.",
            "Vulnerability scores are transparent composites — not validated predictions.",
            "Early-warning models may use precipitation-proxy labels until official events are supplied.",
            "Intervention/cascade outputs are simulations — not guaranteed real-world outcomes.",
            "Federated learning and formal differential privacy are NOT claimed.",
            f"Max upload size: {settings.max_upload_bytes} bytes.",
            f"Data lake: {settings.data_dir}",
        ],
    )

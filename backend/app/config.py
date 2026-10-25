"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. DATABASE_URL must point at PostgreSQL/PostGIS."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        ...,
        alias="DATABASE_URL",
        description="SQLAlchemy URL using psycopg3, e.g. postgresql+psycopg://...",
    )
    backend_host: str = Field(default="0.0.0.0", alias="BACKEND_HOST")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")
    spatial_srid: int = Field(default=4326, alias="SPATIAL_SRID")
    osm_overpass_url: str = Field(
        default="https://overpass-api.de/api/interpreter",
        alias="OSM_OVERPASS_URL",
    )
    osm_request_timeout_seconds: int = Field(
        default=60, alias="OSM_REQUEST_TIMEOUT_SECONDS"
    )
    osm_enabled: bool = Field(default=True, alias="OSM_ENABLED")
    upload_dir: str = Field(default="./backend/data/uploads", alias="UPLOAD_DIR")

    # Module 4 — privacy / robustness
    max_upload_bytes: int = Field(default=5_000_000, alias="MAX_UPLOAD_BYTES")
    rate_limit_window_seconds: int = Field(
        default=60, alias="RATE_LIMIT_WINDOW_SECONDS"
    )
    rate_limit_expensive_per_window: int = Field(
        default=20, alias="RATE_LIMIT_EXPENSIVE_PER_WINDOW"
    )
    environment: str = Field(default="development", alias="APP_ENVIRONMENT")

    # Data lake (raw / processed / models)
    # Prefer paths relative to the backend working directory (uvicorn cwd).
    data_dir: str = Field(default="./data", alias="DATA_DIR")

    # Active study city (see app.cities.registry). Override per-request via APIs.
    default_city_id: str = Field(default="nagpur", alias="DEFAULT_CITY_ID")

    # Optional CDS credentials are read from CDSAPI_URL / CDSAPI_KEY env (never logged).

    # Backward-compatible Nagpur bbox (prefer city registry)
    nagpur_bbox: tuple[float, float, float, float] = (
        78.95,
        21.05,
        79.20,
        21.25,
    )

    @field_validator("database_url")
    @classmethod
    def require_postgres(cls, value: str) -> str:
        lowered = value.lower()
        if "sqlite" in lowered:
            raise ValueError(
                "SQLite is not allowed. Set DATABASE_URL to a PostgreSQL/PostGIS "
                "connection string (postgresql+psycopg://...)."
            )
        if not (
            lowered.startswith("postgresql://")
            or lowered.startswith("postgresql+psycopg://")
            or lowered.startswith("postgresql+psycopg2://")
        ):
            raise ValueError(
                "DATABASE_URL must be a PostgreSQL URL "
                "(prefer postgresql+psycopg://...)."
            )
        if lowered.startswith("postgresql://"):
            return "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

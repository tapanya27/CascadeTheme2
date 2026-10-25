"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import (
    alerts,
    assessments,
    cascade,
    case_center,
    cities,
    dashboard,
    data,
    dependencies,
    early_warning,
    health,
    ingest,
    interventions,
    ml_intelligence,
    reports,
    resilience,
    zones,
)
from app.config import get_settings
from app.database import dispose_engine, get_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    logger.info("Starting CRIVAL API v%s (%s)", __version__, settings.environment)
    logger.info("Spatial SRID=%s", settings.spatial_srid)
    try:
        get_engine()
        logger.info("Database engine initialized")
    except Exception as exc:  # noqa: BLE001
        logger.error("Database engine init failed: %s", type(exc).__name__)
    yield
    dispose_engine()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CRIVAL — Crisis Early-Warning & Vulnerability API",
        description=(
            "City-agnostic spatial intelligence for flood early-warning proxies, "
            "hidden community vulnerability (hazard-only vs multi-factor ranks), "
            "disaster-report intelligence, cascading-failure and resilience simulations. "
            "Requires PostgreSQL with PostGIS. "
            "Forecast likelihood, vulnerability impact, and data-quality confidence "
            "are kept as separate concepts. "
            "Intervention/cascade outputs are simulations — not guaranteed outcomes."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(cities.router)
    app.include_router(zones.router)
    app.include_router(data.router)
    app.include_router(ingest.router)
    app.include_router(assessments.router)
    app.include_router(dependencies.router)
    app.include_router(dashboard.router)
    app.include_router(interventions.router)
    app.include_router(early_warning.router)
    app.include_router(reports.router)
    app.include_router(alerts.router)
    app.include_router(case_center.router)
    app.include_router(cascade.router)
    app.include_router(resilience.router)
    app.include_router(ml_intelligence.router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, exc: Exception):
        logger.exception("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    return app


app = create_app()

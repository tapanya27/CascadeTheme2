"""Pytest fixtures. Integration tests require a live PostgreSQL/PostGIS instance."""

from __future__ import annotations

import os
import sys

import pytest

# Ensure backend package root is on path
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

# Default DATABASE_URL for local docker-compose if not set
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://critical1:critical1_dev@localhost:5433/critical1",
)
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")


@pytest.fixture(scope="session")
def database_available() -> bool:
    from app.database import check_database_health, dispose_engine

    dispose_engine()
    status = check_database_health()
    return status["database"] == "connected" and bool(status["postgis"])


@pytest.fixture
def db_session(database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    from app.database import get_session_factory

    session = get_session_factory()()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


@pytest.fixture
def client(database_available):
    """HTTP test client. Health tests work even if DB is down."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c

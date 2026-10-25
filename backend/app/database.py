"""SQLAlchemy engine and session management for PostgreSQL/PostGIS."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Create (or reuse) the SQLAlchemy engine. PostgreSQL only."""
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            future=True,
        )
        _SessionLocal = sessionmaker(
            bind=_engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and always closes it."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager for scripts and importers."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database_health() -> dict[str, Any]:
    """
    Verify PostgreSQL connectivity and PostGIS availability.
    Raises no exceptions to callers; returns structured status.
    """
    result: dict[str, Any] = {
        "database": "unavailable",
        "postgis": False,
        "postgis_version": None,
        "error": None,
    }
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            result["database"] = "connected"
            try:
                version = conn.execute(
                    text("SELECT PostGIS_Version()")
                ).scalar()
                result["postgis"] = True
                result["postgis_version"] = version
            except SQLAlchemyError as exc:
                result["postgis"] = False
                result["error"] = f"PostGIS not available: {exc}"
    except Exception as exc:  # noqa: BLE001 — surface any connection failure
        result["error"] = str(exc)
    return result


def dispose_engine() -> None:
    """Dispose engine (used in tests / shutdown)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None

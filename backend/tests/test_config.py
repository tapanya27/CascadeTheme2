"""Configuration and SQLite rejection tests."""

import pytest
from pydantic import ValidationError


def test_sqlite_url_rejected(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    from app.config import Settings, get_settings

    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_postgres_url_normalized(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://critical1:critical1_dev@localhost:5432/critical1",
    )
    from app.config import Settings, get_settings

    get_settings.cache_clear()
    s = Settings()  # type: ignore[call-arg]
    assert s.database_url.startswith("postgresql+psycopg://")

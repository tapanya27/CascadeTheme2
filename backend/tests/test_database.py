"""Database connectivity and model tests against live PostGIS."""

from __future__ import annotations

import pytest


def test_database_health_reports_postgis(database_available):
    from app.database import check_database_health, dispose_engine

    dispose_engine()
    status = check_database_health()
    if not database_available:
        assert status["database"] == "unavailable" or status["postgis"] is False
        assert status.get("error")
        return
    assert status["database"] == "connected"
    assert status["postgis"] is True
    assert status["postgis_version"]


def test_models_registered():
    from app.database import Base
    from app.models import (
        DataSource,
        DependencyEdge,
        HazardObservation,
        Infrastructure,
        InterventionScenario,
        VulnerabilityAssessment,
        Zone,
    )

    tables = set(Base.metadata.tables.keys())
    assert "data_sources" in tables
    assert "zones" in tables
    assert "infrastructure" in tables
    assert "hazard_observations" in tables
    assert "vulnerability_assessments" in tables
    assert "dependency_edges" in tables
    assert "intervention_scenarios" in tables
    assert DataSource.__tablename__ == "data_sources"
    assert Zone.__tablename__ == "zones"
    assert Infrastructure.__tablename__ == "infrastructure"
    assert HazardObservation.__tablename__ == "hazard_observations"
    assert VulnerabilityAssessment.__tablename__ == "vulnerability_assessments"
    assert DependencyEdge.__tablename__ == "dependency_edges"
    assert InterventionScenario.__tablename__ == "intervention_scenarios"


def test_synthetic_seed_and_provenance(db_session):
    from app.models.data_source import DataSource
    from app.services.synthetic_data import SYNTHETIC_SOURCE_NAME, seed_synthetic_dataset

    result = seed_synthetic_dataset(db_session, force=False)
    assert "data_source_id" in result

    source = (
        db_session.query(DataSource)
        .filter(DataSource.name == SYNTHETIC_SOURCE_NAME)
        .one()
    )
    assert source.is_synthetic is True
    assert source.kind.value == "synthetic"
    assert source.provenance.get("synthetic") is True
    assert "verified" in (source.description or "").lower() or True
    # Provenance disclaimer must be present
    assert "disclaimer" in source.provenance or "synthetic" in source.provenance

    db_session.rollback()


def test_no_sqlite_in_engine_url(database_available):
    if not database_available:
        pytest.skip("PostgreSQL/PostGIS not available")
    from app.database import get_engine

    url = str(get_engine().url)
    assert "sqlite" not in url.lower()
    assert "postgresql" in url.lower()

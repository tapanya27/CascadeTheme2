"""Unit tests for hybrid ML package (no live Overpass required)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.ml.clusters import build_vulnerability_clusters
from app.ml.embeddings import redact_pii
from app.ml.interventions_rules import recommend_interventions
from app.ml.vulnerability_models import (
    train_isolation_forest,
    transparent_vulnerability_score,
)
from app.ml.zone_dataset import _grid_cells, build_zone_dataset
from app.cities.registry import require_city
from app.ingestion.base import DataLake


def test_redact_pii():
    text = "Call me at +91 98765 43210 or email ada@example.com about flood"
    out = redact_pii(text)
    assert "98765" not in out
    assert "ada@example.com" not in out
    assert "REDACTED" in out


def test_grid_cells_count():
    city = require_city("nagpur")
    cells = _grid_cells(city, n_side=4)
    assert len(cells) == 16
    assert cells[0]["geometry_kind"] == "analysis_grid"
    assert cells[0]["is_synthetic"] is False


def test_transparent_score_and_isolation(tmp_path: Path):
    rows = []
    for i in range(30):
        rows.append(
            {
                "city": "nagpur",
                "zone_id": f"z{i}",
                "latitude": 21.1 + i * 0.01,
                "longitude": 79.0 + i * 0.01,
                "nearest_hospital_km": 1.0 + i * 0.2,
                "road_connectivity": max(0.05, 1.0 - i * 0.03),
                "road_density": 5.0,
                "rainfall_24h_mm": 10.0 + i,
                "rainfall_72h_mm": 20.0 + i,
                "transit_accessibility": i % 5,
                "drainage_indicator": 1,
                "facility_count": max(0, 3 - i // 10),
                "population_density": None,
                "infrastructure_failure_count": None,
                "community_incident_count": None,
                "source_coverage_score": 0.7,
                "data_quality_flag": "medium",
                "is_synthetic": False,
            }
        )
    df = pd.DataFrame(rows)
    scored = transparent_vulnerability_score(df)
    assert "heuristic_vulnerability_score" in scored.columns
    assert scored["heuristic_category"].notna().all()
    report = train_isolation_forest(scored, tmp_path)
    assert report.status == "trained"
    assert (tmp_path / "zone_isolation_forest.joblib").exists()

    clusters = build_vulnerability_clusters(scored, min_category="moderate", eps_km=50)
    assert "meta" in clusters
    assert clusters["type"] == "FeatureCollection"

    recs = recommend_interventions(scored.iloc[-1].to_dict())
    assert isinstance(recs, list) and len(recs) >= 1


def test_build_zone_dataset_skip_overpass(tmp_path: Path, monkeypatch):
    # Point settings data_dir via lake root only
    lake = DataLake(tmp_path)

    # Stub Open-Meteo to avoid network flake
    from app.ml import zone_dataset as zd

    monkeypatch.setattr(
        zd,
        "_fetch_open_meteo_rain",
        lambda *a, **k: {
            "rainfall_24h_mm": 12.5,
            "rainfall_72h_mm": 40.0,
            "rainfall_status": "estimated_city_centroid",
            "rainfall_error": None,
        },
    )
    result = build_zone_dataset(
        lake,
        city_ids=["nagpur", "mumbai"],
        n_side=3,
        skip_overpass=True,
    )
    assert result["success"] is True
    assert result["n_records"] == 3 * 3 * 2
    df = pd.read_parquet(result["parquet"])
    assert "zone_id" in df.columns
    assert df["population_density"].isna().all()
    assert df["rainfall_24h_mm"].notna().all()
    # OSM skipped → road features null (not silently zero-filled as "observed")
    assert df["road_density"].isna().all()

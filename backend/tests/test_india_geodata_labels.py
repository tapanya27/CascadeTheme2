"""Tests for India Geodata inventory label construction (no network)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.ingestion.india_geodata.csv_inventory import (
    _district_token_match,
    _row_matches_city,
    build_labels_from_zenodo_csv,
)
from app.ingestion.india_geodata.manifest import KATHMANDU_NOTE, INDIA_STUDY_CITIES


def test_kathmandu_explicitly_out_of_coverage():
    assert "Nepal" in KATHMANDU_NOTE
    assert "kathmandu" not in INDIA_STUDY_CITIES


def test_district_token_match_exact_not_statewide_noise():
    row = pd.Series(
        {
            "Districts": "Pune, Nagpur, Nashik",
            "Location": "",
            "Latitude": float("nan"),
            "Longitude": float("nan"),
        }
    )
    assert _district_token_match(row, "nagpur") is True
    assert _row_matches_city(row, "chennai") is False


def test_coords_outside_bbox_rejected():
    # Point in Delhi — must not match Nagpur via district text
    row = pd.Series(
        {
            "Districts": "Nagpur",
            "Location": "",
            "Latitude": 28.61,
            "Longitude": 77.21,
        }
    )
    assert _row_matches_city(row, "nagpur") is False


def test_build_labels_from_cached_zenodo_csv():
    data_dir = Path(__file__).resolve().parents[1] / "data"
    csv_path = (
        data_dir
        / "raw"
        / "india_geodata"
        / "flood_inventory_zenodo_csv"
        / "India_Flood_Inventory_v3.csv"
    )
    if not csv_path.exists():
        pytest.skip("Zenodo IFI CSV not cached locally")
    summary = build_labels_from_zenodo_csv(data_dir)
    assert summary["flood_atlas_used_as_labels"] is False
    assert summary["totals"]["usable_temporal_events"] >= 1
    assert summary["totals"]["positives"] >= 1
    # Negatives only in event-bearing years — prevalence should be low but > 0
    assert 0 < summary["totals"]["positive_prevalence"] < 0.5

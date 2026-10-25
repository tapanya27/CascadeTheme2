"""Unit tests for alert dedupe + serialization helpers (no live HTTP)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.services.alerts import (
    SOURCE_DEMO,
    _valid_coords,
    serialize_alert,
)


def test_valid_coords() -> None:
    assert _valid_coords(79.0, 21.1) is True
    assert _valid_coords(None, 21.1) is False
    assert _valid_coords(200.0, 21.1) is False
    assert _valid_coords(79.0, 100.0) is False


def test_serialize_demo_label() -> None:
    row = MagicMock()
    row.id = "00000000-0000-0000-0000-000000000001"
    row.city_id = "nagpur"
    row.source_name = SOURCE_DEMO
    row.source_event_id = "demo-1"
    row.alert_type = "weather_rainfall"
    row.severity = "warning"
    row.title = "Demo: Heavy Rainfall Outlook"
    row.description = "Example only"
    row.lon = 79.08
    row.lat = 21.14
    row.has_reliable_coords = True
    row.zone_id = None
    row.zone_code = None
    row.area_label = "Nagpur"
    row.source_url = None
    row.verification_status = "demo"
    row.authenticity = "demo"
    row.is_demo = True
    row.observed_at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    row.published_at = row.observed_at
    row.ingested_at = row.observed_at
    row.is_read = False
    row.is_acknowledged = False
    row.is_resolved = False
    row.resolved_at = None
    row.extra = {"demo": True}

    out = serialize_alert(row)
    assert out["is_demo"] is True
    assert out["display_label"] == "Demo Alert"
    assert out["authenticity"] == "demo"
    assert out["has_reliable_coords"] is True

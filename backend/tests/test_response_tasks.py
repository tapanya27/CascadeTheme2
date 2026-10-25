"""Unit tests for response task serialization helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.services.response_tasks import PRIORITIES, STATUSES, serialize_task


def test_status_and_priority_sets() -> None:
    assert "open" in STATUSES
    assert "done" in STATUSES
    assert "urgent" in PRIORITIES


def test_serialize_task() -> None:
    row = MagicMock()
    row.id = "00000000-0000-0000-0000-000000000099"
    row.city_id = "nagpur"
    row.zone_id = "00000000-0000-0000-0000-000000000001"
    row.title = "Check hospital access"
    row.description = "Verify road to clinic"
    row.why_recommended = "Travel burden high"
    row.priority = "high"
    row.status = "open"
    row.source = "risk_assessment"
    row.source_ref = "nearest_healthcare_km"
    row.assigned_to = None
    row.next_step = "Call facility"
    row.notes = []
    row.audit = [{"at": "2026-10-26T00:00:00+00:00", "action": "created", "detail": ""}]
    row.completed_at = None
    row.created_at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    row.updated_at = row.created_at

    out = serialize_task(row)
    assert out["title"] == "Check hospital access"
    assert out["status"] == "open"
    assert "not automatic dispatch" in out["disclaimer"].lower()

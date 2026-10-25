"""
Demonstration dataset seeding — delegates to the embedded hardcoded multi-city
dataset so the app works without downloads or manual CSV preparation.

Historical name `seed_synthetic_dataset` kept for API/test compatibility.
Every row is tied to a synthetic DataSource with city_id; Nagpur coordinates
are never copied into other cities.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.hardcoded_seed import (
    SOURCE_NAME_TMPL,
    seed_hardcoded_city,
    seed_hardcoded_dataset,
)

# Backward-compatible alias used by tests that look up the Nagpur source name
SYNTHETIC_SOURCE_NAME = SOURCE_NAME_TMPL.format(city="Nagpur")
NAGPUR_CITY_ID = "nagpur"


def seed_synthetic_dataset(
    db: Session,
    force: bool = False,
    *,
    city_id: Optional[str] = NAGPUR_CITY_ID,
    all_cities: bool = False,
) -> dict[str, Any]:
    """
    Insert hardcoded demonstration zones/infra/hazards/deps/reports.

    Default city_id=nagpur for backward-compatible callers/tests.
    Pass all_cities=True (or use the seed script) to load every city.
    """
    if all_cities:
        return seed_hardcoded_dataset(
            db, city_id=None, all_cities=True, force=force
        )
    return seed_hardcoded_city(db, city_id or NAGPUR_CITY_ID, force=force)

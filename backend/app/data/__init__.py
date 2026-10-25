"""Embedded demonstration datasets (invented / simulated — not verified measurements)."""

from app.data.hardcoded_dataset import (
    DATASET_SEED,
    ZONES_PER_CITY,
    build_city_dataset,
    build_full_dataset,
    list_hardcoded_city_ids,
)

__all__ = [
    "DATASET_SEED",
    "ZONES_PER_CITY",
    "build_city_dataset",
    "build_full_dataset",
    "list_hardcoded_city_ids",
]

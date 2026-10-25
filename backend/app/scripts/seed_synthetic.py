"""
Seed embedded hardcoded demonstration data for all cities.

Usage:
  python -m app.scripts.seed_synthetic
  python -m app.scripts.seed_synthetic --city nagpur
  python -m app.scripts.seed_synthetic --force
"""

from __future__ import annotations

import argparse

from app.database import session_scope
from app.services.synthetic_data import seed_synthetic_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed hardcoded demo dataset")
    parser.add_argument(
        "--city",
        default=None,
        help="Seed a single city id (default: all five cities)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-attempt inserts for missing rows even if a source already exists",
    )
    args = parser.parse_args()
    with session_scope() as db:
        if args.city:
            result = seed_synthetic_dataset(
                db, force=args.force, city_id=args.city, all_cities=False
            )
        else:
            result = seed_synthetic_dataset(
                db, force=args.force, city_id=None, all_cities=True
            )
        print(result)


if __name__ == "__main__":
    main()

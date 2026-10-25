"""
End-to-end India Geodata pipeline (city-scoped).

Usage (from backend/):
  python -m scripts.run_india_geodata_pipeline
  python scripts/run_india_geodata_pipeline.py --skip-download
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ingestion.india_geodata.download import download_selected
from app.ingestion.india_geodata.manifest import (
    EXTERNAL_PORTALS,
    INDIA_STUDY_CITIES,
    KATHMANDU_NOTE,
)
from app.ingestion.india_geodata.clip_and_features import (
    build_zone_static_features,
    clip_flood_inventory,
    clip_wards_and_slums,
    load_flood_atlas_district,
    processed_dir,
)
from app.ingestion.india_geodata.event_labels import build_inventory_labels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(BACKEND / "data"))
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--force-download", action="store_true")
    args = parser.parse_args()
    data_dir = Path(args.data_dir)

    report: dict = {
        "kathmandu_note": KATHMANDU_NOTE,
        "india_study_cities": list(INDIA_STUDY_CITIES),
        "external_portals": EXTERNAL_PORTALS,
    }

    if not args.skip_download:
        keys = [
            "flood_inventory_zenodo_csv",
            "flood_inventory_district_area",
            "flood_inventory",
            "flood_atlas_district_risk",
            "flood_atlas_district_frac",
            "wards_living_atlas",
            "slums_mumbai",
            "slums_tamil_nadu",
            "worldpop_ind_1km",
            "healthcare_facilities",
        ]
        report["download"] = download_selected(
            data_dir, keys=keys, force=args.force_download
        )
    else:
        report["download"] = {"skipped": True}

    # Prefer geojson clip when available; always build CSV-based labels
    report["flood_inventory_clip"] = clip_flood_inventory(data_dir)
    report["wards_slums_clip"] = clip_wards_and_slums(data_dir)
    report["flood_atlas"] = load_flood_atlas_district(data_dir)
    report["labels"] = build_inventory_labels(data_dir)
    # Enrich labels from Zenodo CSV when geojson empty
    from app.ingestion.india_geodata.csv_inventory import (
        build_labels_from_zenodo_csv,
    )

    report["labels_zenodo_csv"] = build_labels_from_zenodo_csv(data_dir)
    from app.ingestion.india_geodata.geojson_labels import (
        build_labels_from_geojson_clips,
    )

    # Prefer spatially strict bbox∩polygon labels for training when geojson present
    report["labels_geojson_bbox"] = build_labels_from_geojson_clips(data_dir)
    report["zone_static_features"] = build_zone_static_features(data_dir)

    from app.ingestion.india_geodata.access_exposure import (
        clip_healthcare,
        join_access_exposure_to_zones,
        sample_worldpop,
    )

    report["healthcare_clip"] = clip_healthcare(data_dir)
    report["worldpop_sample"] = sample_worldpop(data_dir)
    report["zone_features_joined"] = join_access_exposure_to_zones(data_dir)

    # Train if enough labels
    from app.ingestion.india_geodata.train_inventory_model import (
        train_inventory_early_warning,
    )

    report["training"] = train_inventory_early_warning(data_dir)

    out = processed_dir(data_dir) / "pipeline_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"wrote": str(out), "summary_keys": list(report.keys())}, indent=2))
    # Brief human summary
    lab = report.get("labels_zenodo_csv") or report.get("labels") or {}
    totals = lab.get("totals") or {}
    print(
        "USABLE_EVENTS",
        totals.get("usable_temporal_events"),
        "DAILY_POS",
        totals.get("positives"),
        "PREV",
        totals.get("positive_prevalence"),
    )
    tr = report.get("training") or {}
    print("TRAIN_STATUS", tr.get("status"), tr.get("metrics"))


if __name__ == "__main__":
    main()

"""Defensible temporal labels from city-bbox ∩ Flood Inventory GeoJSON polygons."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.cities.registry import require_city
from app.ingestion.india_geodata.clip_and_features import processed_dir
from app.ingestion.india_geodata.event_labels import _parse_date
from app.ingestion.india_geodata.manifest import INDIA_STUDY_CITIES, KATHMANDU_NOTE

try:
    import geopandas as gpd
except ImportError as exc:  # pragma: no cover
    raise ImportError("geopandas required") from exc


def build_labels_from_geojson_clips(data_dir: Path) -> dict[str, Any]:
    out_root = processed_dir(data_dir) / "labels_geojson_bbox"
    out_root.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kathmandu": KATHMANDU_NOTE,
        "flood_atlas_used_as_labels": False,
        "spatial_filter": "inventory polygon intersects city study bbox (EPSG:4326)",
        "label_definition": (
            "Positive: calendar day = event StartDate (parsed) for a polygon that "
            "intersects the city bbox. Negative: other days in the city monsoon "
            "window for years with ≥1 usable intersecting event. "
            "Other days unlabelled (not confirmed non-floods)."
        ),
        "cities": {},
        "totals": {},
    }

    all_events = []
    all_daily = []

    for city_id in INDIA_STUDY_CITIES:
        path = processed_dir(data_dir) / "flood_inventory" / f"{city_id}_events.geojson"
        if not path.exists() or path.stat().st_size < 50:
            summary["cities"][city_id] = {"events": 0, "usable_temporal_events": 0}
            continue
        gdf = gpd.read_file(path)
        events = []
        for idx, row in gdf.iterrows():
            ts = _parse_date(row.get("StartDate"))
            events.append(
                {
                    "city_id": city_id,
                    "fid": row.get("FID"),
                    "event_date": ts,
                    "event_year": int(ts.year) if ts is not None else None,
                    "usable_temporal": ts is not None,
                    "state": row.get("State"),
                    "districts": row.get("Districts"),
                    "main_cause": row.get("MainCause"),
                    "label_source": "india_flood_inventory_v3_geojson_bbox",
                    "not_flood_atlas": True,
                }
            )
        ev = pd.DataFrame(events)
        if len(ev):
            ev.to_parquet(out_root / f"{city_id}_events.parquet", index=False)
            # Mirror into labels_zenodo_csv path consumed by trainer
            zen = processed_dir(data_dir) / "labels_zenodo_csv"
            zen.mkdir(parents=True, exist_ok=True)
            ev.to_parquet(zen / f"{city_id}_events.parquet", index=False)
            all_events.append(ev)
        usable = ev[ev["usable_temporal"]] if len(ev) else ev
        years = (
            sorted({int(y) for y in usable["event_year"].dropna().unique()})
            if len(usable)
            else []
        )
        if city_id == "chennai":
            spans = (("06-01", "09-30"), ("10-01", "12-31"))
        else:
            spans = (("06-01", "09-30"),)
        city = require_city(city_id)
        daily_rows = []
        for y in years:
            event_days = {
                pd.Timestamp(d).normalize()
                for d in usable.loc[usable["event_year"] == y, "event_date"]
                if pd.notna(d)
            }
            days: list[pd.Timestamp] = []
            for a, b in spans:
                days.extend(pd.date_range(f"{y}-{a}", f"{y}-{b}", freq="D"))
            for d in days:
                dn = pd.Timestamp(d).normalize()
                lab = 1 if dn in event_days else 0
                daily_rows.append(
                    {
                        "city_id": city_id,
                        "date": dn,
                        "y_inventory_flood": lab,
                        "label_kind": (
                            "positive_inventory_event"
                            if lab
                            else "negative_monsoon_day_in_event_year"
                        ),
                        "lon": city.centroid[0],
                        "lat": city.centroid[1],
                        "crs": "EPSG:4326",
                        "spatial_support": "polygon_intersects_city_bbox",
                    }
                )
        daily = pd.DataFrame(daily_rows)
        if len(daily):
            daily.to_parquet(out_root / f"{city_id}_daily.parquet", index=False)
            all_daily.append(daily)
        summary["cities"][city_id] = {
            "events_intersecting_bbox": int(len(ev)),
            "usable_temporal_events": int(len(usable)),
            "event_years": years,
            "daily_labelled_rows": int(len(daily)),
            "positives": int(daily["y_inventory_flood"].sum()) if len(daily) else 0,
            "negatives": int((daily["y_inventory_flood"] == 0).sum()) if len(daily) else 0,
        }

    if all_events:
        pd.concat(all_events, ignore_index=True).to_parquet(
            out_root / "all_cities_events.parquet", index=False
        )
    if all_daily:
        dcat = pd.concat(all_daily, ignore_index=True)
        dcat.to_parquet(out_root / "all_cities_daily.parquet", index=False)
        # Also overwrite the path train_inventory_model reads
        zenodo_root = processed_dir(data_dir) / "labels_zenodo_csv"
        zenodo_root.mkdir(parents=True, exist_ok=True)
        dcat.to_parquet(zenodo_root / "all_cities_daily.parquet", index=False)
        if all_events:
            pd.concat(all_events, ignore_index=True).to_parquet(
                zenodo_root / "all_cities_events.parquet", index=False
            )
        summary["totals"] = {
            "usable_temporal_events": int(
                sum(c["usable_temporal_events"] for c in summary["cities"].values())
            ),
            "daily_rows": int(len(dcat)),
            "positives": int(dcat["y_inventory_flood"].sum()),
            "negatives": int((dcat["y_inventory_flood"] == 0).sum()),
            "positive_prevalence": float(dcat["y_inventory_flood"].mean()),
        }
    else:
        summary["totals"] = {
            "usable_temporal_events": 0,
            "daily_rows": 0,
            "positives": 0,
            "negatives": 0,
            "positive_prevalence": None,
        }

    (out_root / "label_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    return summary

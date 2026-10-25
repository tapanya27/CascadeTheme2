"""
City AOI clipping and feature assembly from India Geodata caches.

Does not invent missing observations. Nulls remain null.
Flood Atlas fields are stored as `atlas_*` and never used as event labels.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.cities.registry import require_city
from app.ingestion.india_geodata.manifest import INDIA_STUDY_CITIES, KATHMANDU_NOTE

try:
    import geopandas as gpd
    from shapely.geometry import box, Point
except ImportError as exc:  # pragma: no cover
    raise ImportError("geopandas + shapely required for India Geodata clipping") from exc


def processed_dir(data_dir: Path) -> Path:
    d = Path(data_dir) / "processed" / "india_geodata"
    d.mkdir(parents=True, exist_ok=True)
    return d


def raw_asset_path(data_dir: Path, key: str, filename: str) -> Path:
    return Path(data_dir) / "raw" / "india_geodata" / key / filename


def city_bbox_polygon(city_id: str):
    city = require_city(city_id)
    w, s, e, n = city.bbox
    return box(w, s, e, n)


def clip_flood_inventory(data_dir: Path) -> dict[str, Any]:
    """Filter inventory polygons to India study cities; write per-city GeoJSON + CSV."""
    src = raw_asset_path(
        data_dir, "flood_inventory", "INDIA_FLOOD_INVENTORY_V3.geojson"
    )
    report: dict[str, Any] = {
        "source": str(src),
        "exists": src.exists(),
        "cities": {},
        "kathmandu": KATHMANDU_NOTE,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if not src.exists():
        report["error"] = "Flood inventory not downloaded"
        return report

    gdf = gpd.read_file(src)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    else:
        gdf = gdf.to_crs(4326)

    report["national_features"] = int(len(gdf))
    report["columns"] = list(gdf.columns)

    # Parse dates if present
    date_cols = [c for c in gdf.columns if "date" in c.lower() or c.lower() in {"year", "start", "end", "bdate", "edate"}]
    report["date_columns_detected"] = date_cols

    out_root = processed_dir(data_dir) / "flood_inventory"
    out_root.mkdir(parents=True, exist_ok=True)

    total_retained = 0
    for city_id in INDIA_STUDY_CITIES:
        poly = city_bbox_polygon(city_id)
        # Intersects study bbox
        try:
            hit = gdf[gdf.intersects(poly)].copy()
        except Exception:
            # Some invalid geoms
            gdf2 = gdf[gdf.geometry.notna() & gdf.is_valid].copy()
            hit = gdf2[gdf2.intersects(poly)].copy()

        city = require_city(city_id)
        hit["city_id"] = city_id
        hit["study_bbox"] = str(city.bbox)
        hit["observation_kind"] = "observed_inventory"
        hit["label_family"] = "india_flood_inventory"
        hit["not_flood_atlas"] = True

        geo_path = out_root / f"{city_id}_events.geojson"
        csv_path = out_root / f"{city_id}_events.csv"
        if len(hit) > 0:
            hit.to_file(geo_path, driver="GeoJSON")
            attrs = hit.drop(columns="geometry", errors="ignore")
            attrs.to_csv(csv_path, index=False)
        else:
            # empty marker
            csv_path.write_text("city_id\n", encoding="utf-8")
            geo_path.write_text(
                json.dumps({"type": "FeatureCollection", "features": []}),
                encoding="utf-8",
            )

        n = int(len(hit))
        total_retained += n
        report["cities"][city_id] = {
            "events_intersecting_bbox": n,
            "geojson": str(geo_path),
            "csv": str(csv_path),
        }

    report["total_events_retained_all_cities"] = total_retained
    (out_root / "clip_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _load_wards(data_dir: Path) -> Optional[Any]:
    path = raw_asset_path(data_dir, "wards_living_atlas", "LivingAtlas_Wards.parquet")
    if not path.exists():
        return None
    gdf = gpd.read_parquet(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    else:
        gdf = gdf.to_crs(4326)
    return gdf


def clip_wards_and_slums(data_dir: Path) -> dict[str, Any]:
    report: dict[str, Any] = {"cities": {}, "created_at": datetime.now(timezone.utc).isoformat()}
    wards = _load_wards(data_dir)
    out_root = processed_dir(data_dir) / "wards_slums"
    out_root.mkdir(parents=True, exist_ok=True)

    slum_sources = {
        "mumbai": raw_asset_path(
            data_dir, "slums_mumbai", "UMD_Mumbai_Slum_Boundaries_2016.parquet"
        ),
        "chennai": raw_asset_path(
            data_dir, "slums_tamil_nadu", "TNGIS_TN_Slum_Boundaries.parquet"
        ),
    }

    for city_id in INDIA_STUDY_CITIES:
        city = require_city(city_id)
        poly = city_bbox_polygon(city_id)
        entry: dict[str, Any] = {"city_id": city_id, "bbox": city.bbox}

        if wards is not None:
            try:
                w = wards[wards.intersects(poly)].copy()
            except Exception:
                w = wards.iloc[0:0].copy()
            wpath = out_root / f"{city_id}_wards.geojson"
            if len(w) > 0:
                w.to_file(wpath, driver="GeoJSON")
            entry["wards_count"] = int(len(w))
            entry["wards_path"] = str(wpath)
        else:
            entry["wards_count"] = None
            entry["wards_error"] = "LivingAtlas_Wards.parquet not available"

        if city_id in slum_sources and slum_sources[city_id].exists():
            sg = gpd.read_parquet(slum_sources[city_id])
            if sg.crs is None:
                sg = sg.set_crs(4326)
            else:
                sg = sg.to_crs(4326)
            try:
                sc = sg[sg.intersects(poly)].copy()
            except Exception:
                sc = sg.iloc[0:0].copy()
            spath = out_root / f"{city_id}_slums.geojson"
            if len(sc) > 0:
                sc.to_file(spath, driver="GeoJSON")
            entry["slums_count"] = int(len(sc))
            entry["slums_path"] = str(spath)
        else:
            entry["slums_count"] = 0
            entry["slums_note"] = "No city-specific slum layer in downloaded set"

        report["cities"][city_id] = entry

    (out_root / "clip_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def load_flood_atlas_district(data_dir: Path) -> dict[str, Any]:
    """Load model-derived Flood Atlas JSON — never merge into inventory labels."""
    out: dict[str, Any] = {"kind": "model_derived_flood_atlas", "files": {}}
    for key, fname in (
        ("risk", "District_Wise_flood_risk_data.json"),
        ("max_frac", "District_Wise_max_flood_area_frac.json"),
    ):
        path = raw_asset_path(
            data_dir,
            "flood_atlas_district_risk" if key == "risk" else "flood_atlas_district_frac",
            fname,
        )
        # risk and frac may share folder naming from manifest
        if not path.exists():
            alt = (
                Path(data_dir)
                / "raw"
                / "india_geodata"
                / ("flood_atlas_district_risk" if key == "risk" else "flood_atlas_district_frac")
                / fname
            )
            path = alt
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                out["files"][key] = {
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "n_records": len(data) if isinstance(data, list) else (
                        len(data.keys()) if isinstance(data, dict) else None
                    ),
                    "sample_type": type(data).__name__,
                }
            except json.JSONDecodeError as exc:
                out["files"][key] = {"path": str(path), "error": str(exc)}
        else:
            out["files"][key] = {"missing": True, "expected": str(path)}
    dest = processed_dir(data_dir) / "flood_atlas_summary.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def build_zone_static_features(data_dir: Path) -> dict[str, Any]:
    """
    Build per-city zone feature table from hardcoded/demo zones in processed clips
    + Open-Meteo rainfall history already on disk when present.

    Inventory event counts are exposure/history features, NOT the same as Atlas risk.
    """
    from app.data.hardcoded_dataset import build_city_dataset

    inv_report_path = processed_dir(data_dir) / "flood_inventory" / "clip_report.json"
    inv_report = {}
    if inv_report_path.exists():
        inv_report = json.loads(inv_report_path.read_text(encoding="utf-8"))
    zenodo_label_path = processed_dir(data_dir) / "labels_zenodo_csv" / "label_summary.json"
    zenodo_labels = {}
    if zenodo_label_path.exists():
        zenodo_labels = json.loads(zenodo_label_path.read_text(encoding="utf-8"))

    wards_report_path = processed_dir(data_dir) / "wards_slums" / "clip_report.json"
    wards_report = {}
    if wards_report_path.exists():
        wards_report = json.loads(wards_report_path.read_text(encoding="utf-8"))

    rows: list[dict[str, Any]] = []
    for city_id in INDIA_STUDY_CITIES:
        ds = build_city_dataset(city_id)
        n_events = (
            inv_report.get("cities", {}).get(city_id, {}).get("events_intersecting_bbox")
        )
        if n_events in (None, 0):
            n_events = (
                zenodo_labels.get("cities", {})
                .get(city_id, {})
                .get("usable_temporal_events")
            )
        n_wards = wards_report.get("cities", {}).get(city_id, {}).get("wards_count")
        n_slums = wards_report.get("cities", {}).get(city_id, {}).get("slums_count")

        # Load event centroids distances if events exist
        events_path = (
            processed_dir(data_dir) / "flood_inventory" / f"{city_id}_events.geojson"
        )
        event_gdf = None
        if events_path.exists() and events_path.stat().st_size > 50:
            try:
                event_gdf = gpd.read_file(events_path)
            except Exception:
                event_gdf = None

        for z in ds["zones"]:
            lon = z["centroid"]["lon"]
            lat = z["centroid"]["lat"]
            props = z["properties"]
            dist_km = None
            if event_gdf is not None and len(event_gdf) > 0:
                try:
                    # approximate degree→km
                    cents = event_gdf.geometry.centroid
                    d2 = (cents.x - lon) ** 2 + (cents.y - lat) ** 2
                    dist_km = float(np.sqrt(d2.min()) * 111.0)
                except Exception:
                    dist_km = None

            rows.append(
                {
                    "city_id": city_id,
                    "zone_code": z["code"],
                    "lon": lon,
                    "lat": lat,
                    "crs": "EPSG:4326",
                    "population_est_demo": props.get("population"),
                    "flood_exposure_index_demo": props.get("flood_exposure_index"),
                    "inventory_events_in_city_bbox": n_events,
                    "distance_to_nearest_inventory_event_km": dist_km,
                    "wards_in_city_bbox": n_wards,
                    "slums_in_city_bbox": n_slums,
                    "atlas_joined": False,  # district join optional later
                    "feature_sources": "hardcoded_zones+inventory_clip+wards_clip",
                    "observation_kind": "mixed_simulated_zone_geometry_observed_inventory_counts",
                }
            )

    df = pd.DataFrame(rows)
    out = processed_dir(data_dir) / "zone_static_features.parquet"
    df.to_parquet(out, index=False)
    meta = {
        "path": str(out),
        "n_rows": int(len(df)),
        "n_cols": int(len(df.columns)),
        "columns": list(df.columns),
        "cities": list(INDIA_STUDY_CITIES),
        "note": (
            "Zone geometries remain demo/hardcoded for aggregation scaffolding; "
            "inventory event counts/distances are from real Flood Inventory clips."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (processed_dir(data_dir) / "zone_static_features_meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return meta

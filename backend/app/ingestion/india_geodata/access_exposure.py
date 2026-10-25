"""City-clipped healthcare access + WorldPop density sampling."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.cities.registry import require_city
from app.data.hardcoded_dataset import build_city_dataset
from app.ingestion.india_geodata.clip_and_features import processed_dir
from app.ingestion.india_geodata.manifest import INDIA_STUDY_CITIES

try:
    import geopandas as gpd
    from shapely.geometry import Point, box
except ImportError as exc:  # pragma: no cover
    raise ImportError("geopandas required") from exc


def clip_healthcare(data_dir: Path) -> dict[str, Any]:
    src = (
        Path(data_dir)
        / "raw"
        / "india_geodata"
        / "healthcare_facilities"
        / "INDIA_HEALTH_FACILITIES_NIC.geojson"
    )
    out_root = processed_dir(data_dir) / "healthcare"
    out_root.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "source": str(src),
        "exists": src.exists(),
        "cities": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "crs": "EPSG:4326",
    }
    if not src.exists():
        report["error"] = "healthcare geojson missing"
        return report

    # Large file — read once
    gdf = gpd.read_file(src)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    else:
        gdf = gdf.to_crs(4326)
    report["national_features"] = int(len(gdf))

    for city_id in INDIA_STUDY_CITIES:
        city = require_city(city_id)
        poly = box(*city.bbox)
        try:
            hit = gdf[gdf.intersects(poly)].copy()
        except Exception:
            hit = gdf.iloc[0:0].copy()
        path = out_root / f"{city_id}_healthcare.geojson"
        if len(hit) > 0:
            hit.to_file(path, driver="GeoJSON")
        report["cities"][city_id] = {
            "facilities": int(len(hit)),
            "path": str(path),
        }
    (out_root / "clip_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def sample_worldpop(data_dir: Path) -> dict[str, Any]:
    tif = (
        Path(data_dir)
        / "raw"
        / "india_geodata"
        / "worldpop_ind_1km"
        / "ind_pd_2020_1km.tif"
    )
    report: dict[str, Any] = {
        "source": str(tif),
        "exists": tif.exists(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resolution": "approx_1km",
        "crs": "EPSG:4326",
        "units": "people_per_km2",
    }
    if not tif.exists():
        report["error"] = "WorldPop GeoTIFF missing"
        return report

    try:
        import rasterio
        from rasterio.sample import sample_gen
    except ImportError:
        report["error"] = "rasterio not installed — cannot sample WorldPop"
        return report

    rows = []
    with rasterio.open(tif) as ds:
        report["raster_crs"] = str(ds.crs)
        report["raster_bounds"] = list(ds.bounds)
        report["raster_width"] = ds.width
        report["raster_height"] = ds.height
        for city_id in INDIA_STUDY_CITIES:
            ds_city = build_city_dataset(city_id)
            coords = [
                (z["centroid"]["lon"], z["centroid"]["lat"]) for z in ds_city["zones"]
            ]
            samples = list(sample_gen(ds, coords))
            for z, vals in zip(ds_city["zones"], samples):
                val = float(vals[0]) if vals is not None else None
                if val is not None and (val < -1e20 or np.isnan(val)):
                    val = None
                rows.append(
                    {
                        "city_id": city_id,
                        "zone_code": z["code"],
                        "lon": z["centroid"]["lon"],
                        "lat": z["centroid"]["lat"],
                        "worldpop_density_2020": val,
                        "source": "worldpop_ind_pd_2020_1km",
                        "observation_kind": "modeled_population_density",
                    }
                )

    df = pd.DataFrame(rows)
    out = processed_dir(data_dir) / "worldpop_zone_samples.parquet"
    df.to_parquet(out, index=False)
    report["path"] = str(out)
    report["n_rows"] = int(len(df))
    report["non_null"] = int(df["worldpop_density_2020"].notna().sum())
    (processed_dir(data_dir) / "worldpop_sample_report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    return report


def join_access_exposure_to_zones(data_dir: Path) -> dict[str, Any]:
    """Augment zone_static_features with WorldPop + nearest healthcare distance."""
    zone_path = processed_dir(data_dir) / "zone_static_features.parquet"
    if not zone_path.exists():
        return {"error": "zone_static_features.parquet missing — run clip_and_features first"}
    zones = pd.read_parquet(zone_path)

    wp_path = processed_dir(data_dir) / "worldpop_zone_samples.parquet"
    if wp_path.exists():
        wp = pd.read_parquet(wp_path)
        zones = zones.merge(
            wp[["city_id", "zone_code", "worldpop_density_2020"]],
            on=["city_id", "zone_code"],
            how="left",
        )
    else:
        zones["worldpop_density_2020"] = None

    # Healthcare nearest distance (km) per zone centroid
    hc_root = processed_dir(data_dir) / "healthcare"
    dist_rows = []
    for city_id in INDIA_STUDY_CITIES:
        hc_path = hc_root / f"{city_id}_healthcare.geojson"
        zsub = zones[zones["city_id"] == city_id]
        if not hc_path.exists() or zsub.empty:
            for _, z in zsub.iterrows():
                dist_rows.append(
                    {
                        "city_id": city_id,
                        "zone_code": z["zone_code"],
                        "nearest_healthcare_km": None,
                        "healthcare_count_in_bbox": 0,
                    }
                )
            continue
        hc = gpd.read_file(hc_path)
        n = int(len(hc))
        for _, z in zsub.iterrows():
            if n == 0:
                dist_rows.append(
                    {
                        "city_id": city_id,
                        "zone_code": z["zone_code"],
                        "nearest_healthcare_km": None,
                        "healthcare_count_in_bbox": 0,
                    }
                )
                continue
            # approx degree distance
            d2 = (hc.geometry.x - z["lon"]) ** 2 + (hc.geometry.y - z["lat"]) ** 2
            dist_km = float(np.sqrt(d2.min()) * 111.0)
            dist_rows.append(
                {
                    "city_id": city_id,
                    "zone_code": z["zone_code"],
                    "nearest_healthcare_km": dist_km,
                    "healthcare_count_in_bbox": n,
                }
            )
    dist_df = pd.DataFrame(dist_rows)
    zones = zones.merge(dist_df, on=["city_id", "zone_code"], how="left")
    out = processed_dir(data_dir) / "zone_features_india_geodata.parquet"
    zones.to_parquet(out, index=False)
    meta = {
        "path": str(out),
        "n_rows": int(len(zones)),
        "columns": list(zones.columns),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "notes": (
            "Flood hazard labels remain in labels_zenodo_csv; this table is for "
            "community vulnerability / exposure ranking — not flood onset prediction."
        ),
    }
    (processed_dir(data_dir) / "zone_features_india_geodata_meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return meta

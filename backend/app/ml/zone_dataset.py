"""Reproducible multi-city zone-level observation builder.

Produces analysis-grid zone rows for all registry cities using:
- Open-Meteo historical precipitation (city centroid → estimated zone assign)
- OSM Overpass amenity / road / transit / waterway counts (when reachable)

Does not invent population, failure events, or coordinates outside city bboxes.
Synthetic demo rows are written to a separate file when requested.
"""

from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
import numpy as np
import pandas as pd

from app.cities.registry import BUILTIN_CITIES, CityProfile, list_cities
from app.ingestion.base import DataLake, ProvenanceRecord, utcnow
from app.ml.feature_catalog import CORE_NUMERIC_FEATURES, FEATURE_CATALOG

logger = logging.getLogger(__name__)

PROVIDER_ID = "zone_vulnerability"
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
DEFAULT_OVERPASS = "https://overpass-api.de/api/interpreter"
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]


def _grid_cells(
    city: CityProfile, *, n_side: int
) -> list[dict[str, Any]]:
    west, south, east, north = city.bbox
    cells: list[dict[str, Any]] = []
    lon_edges = np.linspace(west, east, n_side + 1)
    lat_edges = np.linspace(south, north, n_side + 1)
    for i in range(n_side):
        for j in range(n_side):
            w, e = float(lon_edges[j]), float(lon_edges[j + 1])
            s, n = float(lat_edges[i]), float(lat_edges[i + 1])
            lon = (w + e) / 2.0
            lat = (s + n) / 2.0
            # Approximate area in km^2 (equirectangular)
            km_lon = 111.32 * math.cos(math.radians(lat)) * (e - w)
            km_lat = 110.57 * (n - s)
            area_km2 = max(km_lon * km_lat, 1e-6)
            zone_id = f"{city.id}-G{i:02d}{j:02d}"
            cells.append(
                {
                    "city": city.id,
                    "zone_id": zone_id,
                    "latitude": round(lat, 6),
                    "longitude": round(lon, 6),
                    "bbox_west": w,
                    "bbox_south": s,
                    "bbox_east": e,
                    "bbox_north": n,
                    "area_km2": round(area_km2, 6),
                    "geometry_kind": "analysis_grid",
                    "is_synthetic": False,
                }
            )
    return cells


def _fetch_open_meteo_rain(
    lon: float,
    lat: float,
    *,
    end: Optional[datetime] = None,
    days: int = 3,
    timeout: float = 60.0,
    retries: int = 3,
) -> dict[str, Any]:
    """Return rainfall_24h_mm / rainfall_72h_mm or nulls with error note."""
    end = end or datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "hourly": "precipitation",
        "timezone": "UTC",
    }
    last_err: Optional[str] = None
    for attempt in range(retries):
        try:
            with httpx.Client(timeout=timeout) as client:
                r = client.get(OPEN_METEO_URL, params=params)
                r.raise_for_status()
                payload = r.json()
            hourly = payload.get("hourly") or {}
            precip = hourly.get("precipitation") or []
            vals = [float(x) for x in precip if x is not None]
            if not vals:
                return {
                    "rainfall_24h_mm": None,
                    "rainfall_72h_mm": None,
                    "rainfall_status": "unavailable",
                    "rainfall_error": "empty precipitation series",
                }
            rain_24 = float(np.nansum(vals[-24:])) if len(vals) >= 1 else None
            rain_72 = float(np.nansum(vals[-72:])) if len(vals) >= 1 else None
            return {
                "rainfall_24h_mm": round(rain_24, 3) if rain_24 is not None else None,
                "rainfall_72h_mm": round(rain_72, 3) if rain_72 is not None else None,
                "rainfall_status": "estimated_city_centroid",
                "rainfall_error": None,
                "rainfall_retrieved_at": utcnow().isoformat(),
                "rainfall_source_url": OPEN_METEO_URL,
            }
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(1.5 * (attempt + 1))
    return {
        "rainfall_24h_mm": None,
        "rainfall_72h_mm": None,
        "rainfall_status": "unavailable",
        "rainfall_error": last_err,
    }


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _overpass_query(
    city: CityProfile,
    *,
    overpass_url: str,
    timeout: float = 90.0,
    retries: int = 2,
) -> dict[str, Any]:
    """Fetch compact OSM points/ways for amenities relevant to vulnerability."""
    w, s, e, n = city.bbox
    # Keep query small: nodes for amenities + ways for highway/waterway counts
    q = f"""
    [out:json][timeout:60];
    (
      node["amenity"~"hospital|clinic|doctors"]({s},{w},{n},{e});
      node["highway"="bus_stop"]({s},{w},{n},{e});
      node["public_transport"="platform"]({s},{w},{n},{e});
      node["railway"~"station|halt"]({s},{w},{n},{e});
      way["highway"]({s},{w},{n},{e});
      way["waterway"]({s},{w},{n},{e});
    );
    out center tags;
    """
    headers = {
        "User-Agent": "Critical1Percent/1.0 (research; contact=local-dev)",
        "Accept": "application/json",
    }
    urls = [overpass_url] + [u for u in OVERPASS_MIRRORS if u != overpass_url]
    last_err: Optional[str] = None
    # Prefer a short timeout so unreachable mirrors fail fast
    timeout = min(timeout, 45.0)
    for url in urls:
        for attempt in range(retries):
            try:
                with httpx.Client(timeout=timeout, headers=headers) as client:
                    r = client.post(url, data={"data": q})
                    r.raise_for_status()
                    data = r.json()
                elements = data.get("elements") or []
                hospitals: list[tuple[float, float]] = []
                transit: list[tuple[float, float]] = []
                road_centers: list[tuple[float, float]] = []
                water_centers: list[tuple[float, float]] = []
                for el in elements:
                    tags = el.get("tags") or {}
                    if "lat" in el and "lon" in el:
                        lat, lon = float(el["lat"]), float(el["lon"])
                    elif "center" in el:
                        lat = float(el["center"]["lat"])
                        lon = float(el["center"]["lon"])
                    else:
                        continue
                    amenity = tags.get("amenity", "")
                    highway = tags.get("highway", "")
                    if amenity in {"hospital", "clinic", "doctors"}:
                        hospitals.append((lon, lat))
                    if (
                        highway == "bus_stop"
                        or tags.get("public_transport") == "platform"
                        or tags.get("railway") in {"station", "halt"}
                    ):
                        transit.append((lon, lat))
                    if el.get("type") == "way" and highway:
                        road_centers.append((lon, lat))
                    if el.get("type") == "way" and tags.get("waterway"):
                        water_centers.append((lon, lat))
                return {
                    "status": "ok",
                    "error": None,
                    "hospitals": hospitals,
                    "transit": transit,
                    "roads": road_centers,
                    "waterways": water_centers,
                    "element_count": len(elements),
                    "overpass_url": url,
                    "retrieved_at": utcnow().isoformat(),
                }
            except Exception as exc:  # noqa: BLE001
                last_err = f"{url} :: {type(exc).__name__}: {exc}"
                time.sleep(2.0 * (attempt + 1))
    return {
        "status": "unavailable",
        "error": last_err,
        "hospitals": [],
        "transit": [],
        "roads": [],
        "waterways": [],
        "element_count": 0,
        "retrieved_at": utcnow().isoformat(),
    }


def _point_in_bbox(
    lon: float, lat: float, cell: dict[str, Any]
) -> bool:
    return (
        cell["bbox_west"] <= lon <= cell["bbox_east"]
        and cell["bbox_south"] <= lat <= cell["bbox_north"]
    )


def _enrich_cell(
    cell: dict[str, Any],
    *,
    rain: dict[str, Any],
    osm: dict[str, Any],
    city: Optional[CityProfile] = None,
) -> dict[str, Any]:
    row = dict(cell)
    # Population never invented
    row["population_density"] = None
    row["population_density_status"] = "unavailable"

    # Geometric (not social) features — computed from bbox, never fabricated census
    if city is not None:
        row["distance_from_city_centroid_km"] = round(
            _haversine_km(
                cell["longitude"],
                cell["latitude"],
                city.centroid[0],
                city.centroid[1],
            ),
            4,
        )
    else:
        row["distance_from_city_centroid_km"] = None

    row["rainfall_24h_mm"] = rain.get("rainfall_24h_mm")
    row["rainfall_72h_mm"] = rain.get("rainfall_72h_mm")
    row["rainfall_status"] = rain.get("rainfall_status")
    row["rainfall_error"] = rain.get("rainfall_error")

    if osm.get("status") != "ok":
        row.update(
            {
                "road_density": None,
                "road_connectivity": None,
                "nearest_hospital_km": None,
                "transit_accessibility": None,
                "drainage_indicator": None,
                "facility_count": None,
                "osm_status": "unavailable",
                "osm_error": osm.get("error"),
                "community_incident_count": None,
                "infrastructure_failure_count": None,
            }
        )
    else:
        roads_in = [
            p for p in osm["roads"] if _point_in_bbox(p[0], p[1], cell)
        ]
        water_in = [
            p for p in osm["waterways"] if _point_in_bbox(p[0], p[1], cell)
        ]
        hosp_in = [
            p for p in osm["hospitals"] if _point_in_bbox(p[0], p[1], cell)
        ]
        transit_in = [
            p for p in osm["transit"] if _point_in_bbox(p[0], p[1], cell)
        ]
        area = float(cell["area_km2"])
        road_density = len(roads_in) / area
        # Connectivity proxy: saturate road density into 0–1
        road_connectivity = float(min(1.0, road_density / 20.0))
        # Nearest hospital in city sample (great-circle)
        nearest = None
        for hl, ht in osm["hospitals"]:
            d = _haversine_km(cell["longitude"], cell["latitude"], hl, ht)
            nearest = d if nearest is None else min(nearest, d)
        row.update(
            {
                "road_density": round(road_density, 4),
                "road_connectivity": round(road_connectivity, 4),
                "nearest_hospital_km": (
                    round(nearest, 4) if nearest is not None else None
                ),
                "transit_accessibility": len(transit_in),
                "drainage_indicator": len(water_in),
                "facility_count": len(hosp_in),
                "osm_status": "ok",
                "osm_error": None,
                # Incident/failure layers not in Overpass sample — leave null
                "community_incident_count": None,
                "infrastructure_failure_count": None,
            }
        )

    core_vals = [row.get(k) for k in CORE_NUMERIC_FEATURES if k != "source_coverage_score"]
    present = sum(1 for v in core_vals if v is not None)
    total = len(core_vals)
    coverage = present / total if total else 0.0
    row["source_coverage_score"] = round(coverage, 4)
    if coverage >= 0.75:
        row["data_quality_flag"] = "high"
    elif coverage >= 0.45:
        row["data_quality_flag"] = "medium"
    else:
        row["data_quality_flag"] = "low"
    row["collection_date"] = utcnow().date().isoformat()
    return row


def build_zone_dataset(
    lake: DataLake,
    *,
    city_ids: Optional[list[str]] = None,
    n_side: int = 8,
    overpass_url: str = DEFAULT_OVERPASS,
    skip_overpass: bool = False,
    rain_cache: Optional[dict[str, dict[str, Any]]] = None,
    osm_cache: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Build and persist zone-level parquet + catalog for selected cities."""
    cities = list_cities()
    if city_ids:
        wanted = {c.strip().lower() for c in city_ids}
        cities = [c for c in cities if c.id in wanted]
    if not cities:
        raise ValueError("No cities selected")

    rain_cache = rain_cache if rain_cache is not None else {}
    osm_cache = osm_cache if osm_cache is not None else {}
    rows: list[dict[str, Any]] = []
    city_stats: dict[str, Any] = {}

    out_dir = lake.provider_processed(PROVIDER_ID)
    raw_dir = lake.provider_raw(PROVIDER_ID)

    for city in cities:
        logger.info("Building zone grid for %s (n_side=%s)", city.id, n_side)
        if city.id not in rain_cache:
            rain_cache[city.id] = _fetch_open_meteo_rain(
                city.centroid[0], city.centroid[1]
            )
            lake.write_json(
                raw_dir / f"{city.id}_open_meteo_rain.json", rain_cache[city.id]
            )
        if skip_overpass:
            osm_cache[city.id] = {
                "status": "skipped",
                "error": "skip_overpass=True",
                "hospitals": [],
                "transit": [],
                "roads": [],
                "waterways": [],
                "element_count": 0,
            }
        elif city.id not in osm_cache:
            osm_cache[city.id] = _overpass_query(city, overpass_url=overpass_url)
            # Do not persist raw OSM coordinates dumps at full size in git —
            # store counts only for provenance.
            lake.write_json(
                raw_dir / f"{city.id}_osm_summary.json",
                {
                    "status": osm_cache[city.id]["status"],
                    "error": osm_cache[city.id].get("error"),
                    "element_count": osm_cache[city.id].get("element_count"),
                    "hospital_count": len(osm_cache[city.id].get("hospitals") or []),
                    "transit_count": len(osm_cache[city.id].get("transit") or []),
                    "road_way_count": len(osm_cache[city.id].get("roads") or []),
                    "waterway_count": len(osm_cache[city.id].get("waterways") or []),
                    "retrieved_at": osm_cache[city.id].get("retrieved_at"),
                    "bbox": list(city.bbox),
                },
            )

        cells = _grid_cells(city, n_side=n_side)
        for cell in cells:
            rows.append(
                _enrich_cell(
                    cell,
                    rain=rain_cache[city.id],
                    osm=osm_cache[city.id],
                    city=city,
                )
            )
        city_stats[city.id] = {
            "n_zones": len(cells),
            "rainfall_status": rain_cache[city.id].get("rainfall_status"),
            "osm_status": osm_cache[city.id].get("status"),
            "osm_error": osm_cache[city.id].get("error"),
            "osm_elements": osm_cache[city.id].get("element_count"),
        }

    df = pd.DataFrame(rows)
    parquet_path = out_dir / "zones_features.parquet"
    csv_path = out_dir / "zones_features.csv"
    df.to_parquet(parquet_path, index=False)
    df.to_csv(csv_path, index=False)

    null_rates = {
        c: float(df[c].isna().mean()) if c in df.columns else 1.0
        for c in CORE_NUMERIC_FEATURES
    }
    provenance = ProvenanceRecord(
        provider_id=PROVIDER_ID,
        source_name="Open-Meteo + OSM Overpass analysis grid",
        license_note="Open-Meteo CC BY 4.0; OSM ODbL; analysis grids are project-derived",
        retrieval_url=OPEN_METEO_URL,
        retrieved_at=utcnow().isoformat(),
        version_tag="v1-zone-grid",
        geographic_coverage={
            "cities": [c.id for c in cities],
            "geometry_kind": "analysis_grid",
            "n_side": n_side,
        },
        temporal_coverage={"rainfall_window_days": 3},
        quality_limitations=[
            "Analysis-grid cells are not official wards or census tracts.",
            "Rainfall is city-centroid Open-Meteo, applied to all zones in that city.",
            "Population density is intentionally null until a verified density source is wired.",
            "Community incident / infrastructure failure counts are null unless DB layers exist.",
            "Great-circle hospital distance is not network travel time.",
        ],
        observation_kind="estimated",
        extra={"null_rates": null_rates, "city_stats": city_stats},
    )
    catalog_path = out_dir / "feature_catalog.json"
    lake.write_json(
        catalog_path,
        {
            "features": FEATURE_CATALOG,
            "core_numeric": CORE_NUMERIC_FEATURES,
            "provenance": provenance.to_dict(),
            "n_records": int(len(df)),
            "n_features": int(len(df.columns)),
            "columns": list(df.columns),
            "file_bytes_parquet": parquet_path.stat().st_size,
            "file_bytes_csv": csv_path.stat().st_size,
        },
    )
    lake.write_json(out_dir / "build_report.json", {
        "success": True,
        "n_records": int(len(df)),
        "n_features": int(len(df.columns)),
        "cities": city_stats,
        "parquet": str(parquet_path),
        "csv": str(csv_path),
        "catalog": str(catalog_path),
        "built_at": utcnow().isoformat(),
    })

    return {
        "success": True,
        "n_records": int(len(df)),
        "n_features": int(len(df.columns)),
        "parquet": str(parquet_path),
        "csv": str(csv_path),
        "catalog": str(catalog_path),
        "city_stats": city_stats,
        "null_rates": null_rates,
        "size_bytes": parquet_path.stat().st_size + csv_path.stat().st_size,
    }


def export_postgis_zone_features(
    features: list[dict[str, Any]],
    lake: DataLake,
    *,
    filename: str = "postgis_zones_features.parquet",
) -> dict[str, Any]:
    """Persist features extracted from live PostGIS (separate from analysis grid)."""
    if not features:
        return {"success": False, "message": "No PostGIS zone features to export"}
    out_dir = lake.provider_processed(PROVIDER_ID)
    df = pd.DataFrame(features)
    path = out_dir / filename
    df.to_parquet(path, index=False)
    return {
        "success": True,
        "n_records": len(df),
        "n_features": len(df.columns),
        "parquet": str(path),
        "note": "PostGIS export — separate from analysis_grid dataset.",
    }


def load_zone_dataframe(lake: DataLake) -> pd.DataFrame:
    path = lake.provider_processed(PROVIDER_ID) / "zones_features.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run build_zone_dataset / POST /api/ml/dataset/build first."
        )
    return pd.read_parquet(path)

"""
Construct defensible flood-event labels from India Flood Inventory.

Rules:
- Positives = city-bbox ∩ inventory polygons with usable dates.
- Negatives are NOT "all other days" blindly — use a documented sampling window
  around monsoon seasons with explicit unmarked days excluded from training
  when event coverage is too sparse.
- Flood Atlas values are NEVER used as labels.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.cities.registry import require_city
from app.ingestion.india_geodata.clip_and_features import processed_dir
from app.ingestion.india_geodata.manifest import INDIA_STUDY_CITIES

try:
    import geopandas as gpd
except ImportError as exc:  # pragma: no cover
    raise ImportError("geopandas required") from exc


_DATE_PATTERNS = [
    re.compile(r"(?P<y>19\d{2}|20\d{2})[-/](?P<m>\d{1,2})[-/](?P<d>\d{1,2})"),
    re.compile(r"(?P<d>\d{1,2})[-/](?P<m>\d{1,2})[-/](?P<y>19\d{2}|20\d{2})"),
    re.compile(r"(?P<y>19\d{2}|20\d{2})(?P<m>\d{2})(?P<d>\d{2})"),
]


def _parse_year(val: Any) -> Optional[int]:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    m = re.search(r"(19\d{2}|20\d{2})", s)
    if m:
        y = int(m.group(1))
        if 1960 <= y <= 2025:
            return y
    try:
        y = int(float(s))
        if 1960 <= y <= 2025:
            return y
    except (TypeError, ValueError):
        return None
    return None


def _parse_date(val: Any) -> Optional[pd.Timestamp]:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    if isinstance(val, datetime):
        return pd.Timestamp(val)
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    # pandas flexible parse
    try:
        ts = pd.to_datetime(s, errors="coerce", dayfirst=True)
        if pd.notna(ts):
            return pd.Timestamp(ts)
    except Exception:
        pass
    for pat in _DATE_PATTERNS:
        m = pat.search(s)
        if m:
            y, mo, d = int(m.group("y")), int(m.group("m")), int(m.group("d"))
            try:
                return pd.Timestamp(year=y, month=mo, day=d)
            except ValueError:
                continue
    y = _parse_year(s)
    if y is not None:
        # Year-only → mid-monsoon proxy date (documented assumption)
        return pd.Timestamp(year=y, month=7, day=15)
    return None


def extract_event_table(city_id: str, data_dir: Path) -> pd.DataFrame:
    path = processed_dir(data_dir) / "flood_inventory" / f"{city_id}_events.geojson"
    if not path.exists() or path.stat().st_size < 50:
        return pd.DataFrame()
    gdf = gpd.read_file(path)
    if gdf.empty:
        return pd.DataFrame()

    rows = []
    for idx, row in gdf.iterrows():
        props = {c: row[c] for c in gdf.columns if c != "geometry"}
        # Heuristic field scan
        date_val = None
        year_val = None
        for k, v in props.items():
            lk = str(k).lower()
            if date_val is None and any(
                t in lk for t in ("date", "bdate", "edate", "start", "end", "onset")
            ):
                date_val = _parse_date(v)
            if year_val is None and lk in {"year", "yr", "flood_year"}:
                year_val = _parse_year(v)
        if date_val is None and year_val is not None:
            date_val = pd.Timestamp(year=year_val, month=7, day=15)
            date_precision = "year_mid_monsoon_assumed"
        elif date_val is not None and str(props.get("year", "")).strip() == str(
            getattr(date_val, "year", "")
        ):
            date_precision = "parsed_date_or_year"
        elif date_val is not None:
            date_precision = "parsed"
        else:
            date_precision = "missing"

        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        cent = geom.centroid
        rows.append(
            {
                "city_id": city_id,
                "event_index": int(idx) if isinstance(idx, (int, np.integer)) else idx,
                "event_date": date_val,
                "event_year": int(date_val.year) if date_val is not None else year_val,
                "date_precision": date_precision,
                "usable_temporal": date_val is not None,
                "centroid_lon": float(cent.x),
                "centroid_lat": float(cent.y),
                "area_deg2": float(geom.area) if geom is not None else None,
                "label_source": "india_flood_inventory_v3",
                "label_family": "inventory_event",
                "not_flood_atlas": True,
                "raw_props_keys": ",".join(map(str, props.keys())),
            }
        )
    return pd.DataFrame(rows)


def build_inventory_labels(data_dir: Path) -> dict[str, Any]:
    """
    Produce city event tables + a daily city-level panel for years with events.

    Sampling procedure for negatives (documented):
    - Only years that contain ≥1 usable inventory event in that city bbox.
    - Within those years, monsoon days (Jun–Sep) without an event date match
      are candidate negatives.
    - Days outside event years are LEFT UNLABELLED (not treated as confirmed non-floods).
    """
    out_root = processed_dir(data_dir) / "labels"
    out_root.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "label_definition": (
            "Positive: calendar day matches an inventory event date (or year-mid-monsoon "
            "when only year known) for an event intersecting the city study bbox. "
            "Negative: monsoon day in an event-bearing year with no event match. "
            "Unlabelled: all other days (NOT confirmed non-floods)."
        ),
        "flood_atlas_used_as_labels": False,
        "cities": {},
        "totals": {},
    }

    all_events = []
    all_daily = []

    for city_id in INDIA_STUDY_CITIES:
        ev = extract_event_table(city_id, data_dir)
        ev_path = out_root / f"{city_id}_inventory_events.parquet"
        if len(ev) > 0:
            ev.to_parquet(ev_path, index=False)
            all_events.append(ev)
        usable = ev[ev["usable_temporal"]] if len(ev) else ev
        years = sorted({int(y) for y in usable["event_year"].dropna().unique()}) if len(usable) else []

        daily_rows = []
        for y in years:
            # Monsoon window only
            days = pd.date_range(f"{y}-06-01", f"{y}-09-30", freq="D")
            event_days = set()
            for _, r in usable[usable["event_year"] == y].iterrows():
                if pd.isna(r["event_date"]):
                    continue
                event_days.add(pd.Timestamp(r["event_date"]).normalize())
            for d in days:
                dn = pd.Timestamp(d).normalize()
                if dn in event_days:
                    lab = 1
                    kind = "positive_inventory_event"
                else:
                    lab = 0
                    kind = "negative_monsoon_day_in_event_year"
                daily_rows.append(
                    {
                        "city_id": city_id,
                        "date": dn,
                        "y_inventory_flood": lab,
                        "label_kind": kind,
                        "crs": "EPSG:4326",
                        "spatial_support": "city_bbox",
                        "lon": require_city(city_id).centroid[0],
                        "lat": require_city(city_id).centroid[1],
                    }
                )

        daily = pd.DataFrame(daily_rows)
        daily_path = out_root / f"{city_id}_daily_labels.parquet"
        if len(daily) > 0:
            daily.to_parquet(daily_path, index=False)
            all_daily.append(daily)

        summary["cities"][city_id] = {
            "inventory_polygons_in_bbox": int(len(ev)),
            "usable_temporal_events": int(len(usable)),
            "event_years": years,
            "daily_labelled_rows": int(len(daily)),
            "positives": int(daily["y_inventory_flood"].sum()) if len(daily) else 0,
            "negatives": int((daily["y_inventory_flood"] == 0).sum()) if len(daily) else 0,
            "events_path": str(ev_path) if len(ev) else None,
            "daily_path": str(daily_path) if len(daily) else None,
        }

    if all_events:
        cat = pd.concat(all_events, ignore_index=True)
        cat.to_parquet(out_root / "all_cities_inventory_events.parquet", index=False)
    if all_daily:
        dcat = pd.concat(all_daily, ignore_index=True)
        dcat.to_parquet(out_root / "all_cities_daily_labels.parquet", index=False)
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

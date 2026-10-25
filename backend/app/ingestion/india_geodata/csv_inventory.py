"""
Build city-filtered labels from Zenodo IFI-Impacts CSV (no polygons required).

District/state name matching against study cities. Events without usable dates
are counted but not used as temporal positives.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from app.cities.registry import require_city
from app.ingestion.india_geodata.clip_and_features import processed_dir
from app.ingestion.india_geodata.event_labels import _parse_date, _parse_year
from app.ingestion.india_geodata.manifest import INDIA_STUDY_CITIES, KATHMANDU_NOTE

# Prefer coordinate-in-bbox; else exact district / location tokens (not statewide floods).
CITY_DISTRICT_TOKENS: dict[str, tuple[str, ...]] = {
    "nagpur": ("nagpur",),
    "mumbai": ("mumbai", "mumbai suburban", "bombay", "mumbai city"),
    "chennai": ("chennai", "madras"),
    "guwahati": ("guwahati", "kamrup metropolitan", "kamrup metro", "gauhati"),
}


def _zenodo_csv_path(data_dir: Path) -> Path:
    return (
        Path(data_dir)
        / "raw"
        / "india_geodata"
        / "flood_inventory_zenodo_csv"
        / "India_Flood_Inventory_v3.csv"
    )


def _coords_in_city_bbox(row: pd.Series, city_id: str) -> Optional[bool]:
    """Return True/False if lat/lon present; None if missing."""
    try:
        lat = float(row.get("Latitude"))
        lon = float(row.get("Longitude"))
    except (TypeError, ValueError):
        return None
    if lat != lat or lon != lon:  # NaN
        return None
    city = require_city(city_id)
    w, s, e, n = city.bbox
    return bool(w <= lon <= e and s <= lat <= n)


def _district_token_match(row: pd.Series, city_id: str) -> bool:
    tokens = CITY_DISTRICT_TOKENS[city_id]
    districts = str(row.get("Districts") or "")
    location = str(row.get("Location") or "")
    # Split district lists on commas; require token equality / startswith
    parts = [p.strip().lower() for p in districts.replace(";", ",").split(",") if p.strip()]
    loc = location.strip().lower()
    for tok in tokens:
        if loc == tok or loc.startswith(tok + " ") or tok in loc.split():
            return True
        for p in parts:
            if p == tok or p.startswith(tok + " ") or p.endswith(" " + tok):
                return True
            # allow "Mumbai Suburban" etc.
            if tok in p.split() and len(p) <= 40:
                return True
    return False


def _row_matches_city(row: pd.Series, city_id: str) -> bool:
    coord = _coords_in_city_bbox(row, city_id)
    if coord is True:
        return True
    if coord is False:
        # Explicit point outside bbox — do not rescue via statewide district lists
        return False
    return _district_token_match(row, city_id)


def _pick_date(row: pd.Series) -> tuple[Optional[pd.Timestamp], str]:
    for col in row.index:
        lc = str(col).lower()
        if any(k in lc for k in ("date", "start", "onset", "begin")):
            ts = _parse_date(row[col])
            if ts is not None:
                return ts, f"col:{col}"
    for col in row.index:
        lc = str(col).lower()
        if lc in {"year", "yr", "flood_year"}:
            y = _parse_year(row[col])
            if y is not None:
                return pd.Timestamp(year=y, month=7, day=15), f"year_mid_monsoon:{col}"
    return None, "missing"


def build_labels_from_zenodo_csv(data_dir: Path) -> dict[str, Any]:
    src = _zenodo_csv_path(data_dir)
    out_root = processed_dir(data_dir) / "labels_zenodo_csv"
    out_root.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(src),
        "source_exists": src.exists(),
        "kathmandu": KATHMANDU_NOTE,
        "flood_atlas_used_as_labels": False,
        "label_definition": (
            "Positive: monsoon calendar day matching an IFI-Impacts event date "
            "(or mid-monsoon day when only year is known) for rows whose "
            "district/state/place text matches the study city tokens. "
            "Negative: other Jun–Sep days in years that contain ≥1 usable city event. "
            "Days outside event-bearing years remain unlabelled (not confirmed non-floods)."
        ),
        "cities": {},
        "totals": {},
        "columns": [],
    }
    if not src.exists():
        summary["error"] = "Zenodo IFI CSV not downloaded"
        (out_root / "label_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        return summary

    df = pd.read_csv(src)
    summary["columns"] = list(df.columns)
    summary["national_rows"] = int(len(df))

    all_events = []
    all_daily = []

    for city_id in INDIA_STUDY_CITIES:
        mask = df.apply(lambda r: _row_matches_city(r, city_id), axis=1)
        sub = df.loc[mask].copy()
        events = []
        for i, row in sub.iterrows():
            ts, precision = _pick_date(row)
            events.append(
                {
                    "city_id": city_id,
                    "source_row": int(i) if isinstance(i, (int,)) else i,
                    "event_date": ts,
                    "event_year": int(ts.year) if ts is not None else _parse_year(
                        row.get("Year") if hasattr(row, "get") else None
                    ),
                    "date_precision": precision,
                    "usable_temporal": ts is not None,
                    "label_source": "zenodo_ifi_impacts_v3_csv",
                    "label_family": "inventory_event",
                    "not_flood_atlas": True,
                    "matched_via": "district_state_text_tokens",
                }
            )
        ev = pd.DataFrame(events)
        if len(ev):
            # fill year from date
            ev["event_year"] = ev.apply(
                lambda r: int(r["event_date"].year)
                if pd.notna(r["event_date"])
                else r["event_year"],
                axis=1,
            )
            ev.to_parquet(out_root / f"{city_id}_events.parquet", index=False)
            all_events.append(ev)

        usable = ev[ev["usable_temporal"]] if len(ev) else ev
        years = (
            sorted({int(y) for y in usable["event_year"].dropna().unique()})
            if len(usable)
            else []
        )

        daily_rows = []
        city = require_city(city_id)
        # Chennai: NE monsoon (Oct–Dec) is primary; others: SW monsoon (Jun–Sep)
        if city_id == "chennai":
            season_spans = (("06-01", "09-30"), ("10-01", "12-31"))
        else:
            season_spans = (("06-01", "09-30"),)

        for y in years:
            event_days = {
                pd.Timestamp(d).normalize()
                for d in usable.loc[usable["event_year"] == y, "event_date"]
                if pd.notna(d)
            }
            day_index: list[pd.Timestamp] = []
            for a, b in season_spans:
                day_index.extend(pd.date_range(f"{y}-{a}", f"{y}-{b}", freq="D"))
            for d in day_index:
                dn = pd.Timestamp(d).normalize()
                lab = 1 if dn in event_days else 0
                daily_rows.append(
                    {
                        "city_id": city_id,
                        "date": dn,
                        "y_inventory_flood": lab,
                        "label_kind": (
                            "positive_inventory_event"
                            if lab == 1
                            else "negative_monsoon_day_in_event_year"
                        ),
                        "lon": city.centroid[0],
                        "lat": city.centroid[1],
                        "crs": "EPSG:4326",
                        "spatial_support": "district_name_match_or_point_in_bbox",
                    }
                )
        daily = pd.DataFrame(daily_rows)
        if len(daily):
            daily.to_parquet(out_root / f"{city_id}_daily.parquet", index=False)
            all_daily.append(daily)

        summary["cities"][city_id] = {
            "csv_rows_matched": int(len(sub)),
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

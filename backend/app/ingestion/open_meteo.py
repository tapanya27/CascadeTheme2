"""Open-Meteo Historical Weather — precipitation features without API keys."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
import pandas as pd

from app.ingestion.base import DataLake, IngestResult, IngestionProvider, ProvenanceRecord, utcnow

logger = logging.getLogger(__name__)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


class OpenMeteoPrecipitationProvider(IngestionProvider):
    provider_id = "open_meteo_archive"
    source_name = "Open-Meteo Historical Weather API"
    license_note = "CC BY 4.0 — attribution required (https://open-meteo.com/)"

    def ingest(
        self,
        *,
        lon: float,
        lat: float,
        start: date,
        end: date,
        city_id: Optional[str] = None,
        force: bool = False,
        include_soil_moisture: bool = False,
    ) -> IngestResult:
        if end < start:
            return IngestResult(
                success=False,
                provider_id=self.provider_id,
                message="end date must be >= start date",
            )
        # Bound downloads — refuse multi-year unbounded pulls in one call
        if (end - start).days > 400:
            return IngestResult(
                success=False,
                provider_id=self.provider_id,
                message="Date range exceeds 400 days; split into batches.",
            )

        tag = f"{city_id or 'point'}_{lon:.3f}_{lat:.3f}_{start.isoformat()}_{end.isoformat()}"
        raw_path = self.lake.provider_raw(self.provider_id) / f"{tag}.json"
        processed_path = self.lake.provider_processed(self.provider_id) / f"{tag}_hourly.parquet"

        if not force and self.cache_valid(raw_path) and self.cache_valid(processed_path):
            return IngestResult(
                success=True,
                provider_id=self.provider_id,
                message="Reused valid cached Open-Meteo download.",
                raw_path=str(raw_path),
                processed_path=str(processed_path),
                provenance=self._provenance(lon, lat, start, end, city_id, cached=True),
                stats={"cached": True},
            )

        hourly = ["precipitation"]
        if include_soil_moisture:
            hourly.append("soil_moisture_0_to_7cm")

        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "hourly": ",".join(hourly),
            "timezone": "UTC",
        }

        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.get(ARCHIVE_URL, params=params)
                resp.raise_for_status()
                payload = resp.json()
        except httpx.HTTPError as exc:
            return IngestResult(
                success=False,
                provider_id=self.provider_id,
                message=f"Open-Meteo request failed: {type(exc).__name__}",
            )

        if "hourly" not in payload or "time" not in payload["hourly"]:
            return IngestResult(
                success=False,
                provider_id=self.provider_id,
                message="Unexpected Open-Meteo payload (missing hourly.time).",
            )

        self.lake.write_json(raw_path, payload)
        df = self._to_frame(payload)
        # Never coerce missing precip to zero — keep NaN
        df.to_parquet(processed_path, index=False)

        features_path = self.lake.provider_processed(self.provider_id) / f"{tag}_features.parquet"
        feat = build_rainfall_window_features(df)
        feat.to_parquet(features_path, index=False)

        return IngestResult(
            success=True,
            provider_id=self.provider_id,
            message="Downloaded and processed Open-Meteo precipitation.",
            raw_path=str(raw_path),
            processed_path=str(processed_path),
            provenance=self._provenance(lon, lat, start, end, city_id, cached=False),
            stats={
                "rows": int(len(df)),
                "precip_missing": int(df["precipitation"].isna().sum()),
                "features_path": str(features_path),
                "units": {"precipitation": "mm (preceding hour sum)"},
            },
        )

    def _to_frame(self, payload: dict[str, Any]) -> pd.DataFrame:
        hourly = payload["hourly"]
        data = {"time": pd.to_datetime(hourly["time"], utc=True)}
        for key, values in hourly.items():
            if key == "time":
                continue
            data[key] = values
        return pd.DataFrame(data)

    def _provenance(
        self,
        lon: float,
        lat: float,
        start: date,
        end: date,
        city_id: Optional[str],
        *,
        cached: bool,
    ) -> ProvenanceRecord:
        return ProvenanceRecord(
            provider_id=self.provider_id,
            source_name=self.source_name,
            license_note=self.license_note,
            retrieval_url=ARCHIVE_URL,
            retrieved_at=utcnow().isoformat(),
            version_tag="open-meteo-archive-v1",
            geographic_coverage={"lon": lon, "lat": lat, "city_id": city_id},
            temporal_coverage={"start": start.isoformat(), "end": end.isoformat()},
            quality_limitations=[
                "Reanalysis-based historical product — not a live forecast.",
                "Point sample at city centroid; not a spatial precipitation field.",
                "Missing hourly values are preserved as null (never zero-filled).",
            ],
            observation_kind="estimated",
            extra={"cached": cached},
        )


def build_rainfall_window_features(df: pd.DataFrame) -> pd.DataFrame:
    """Rolling rainfall totals. Missing windows stay NaN (no silent zero fill)."""
    if "time" not in df.columns or "precipitation" not in df.columns:
        raise ValueError("DataFrame requires time and precipitation columns")
    out = df.sort_values("time").copy()
    precip = out["precipitation"]
    for hours in (1, 3, 6, 24, 72):
        # min_periods=hours requires full window; else NaN
        out[f"rain_{hours}h"] = precip.rolling(window=hours, min_periods=hours).sum()
    out["doy"] = out["time"].dt.dayofyear
    out["month"] = out["time"].dt.month
    return out


def default_train_window() -> tuple[date, date]:
    """
    Small representative monsoon-season window for prototype training.
    Fixed historical dates avoid drifting into periods with little rain
    and keep downloads reproducible across runs.
    """
    return date(2023, 6, 1), date(2023, 8, 31)

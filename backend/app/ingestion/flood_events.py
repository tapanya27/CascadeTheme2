"""Flood event label providers.

GFD (Earth Engine) and GFID require external auth or unstable hosts.
This module provides:
1) A precipitation-threshold proxy honestly labelled as simulated/estimated.
2) Hooks for loading external GeoJSON/CSV event lists when the user supplies them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd

from app.ingestion.base import DataLake, IngestResult, IngestionProvider, ProvenanceRecord, utcnow

GFD_BLOCKER = (
    "Global Flood Database (MODIS) requires Google Earth Engine authentication. "
    "Authenticate EE separately, or place a GeoJSON/CSV of flood events under "
    "backend/data/raw/flood_events/ and call the local loader. "
    "Until then, precipitation-proxy labels are available and marked as estimated."
)


class FloodEventProxyProvider(IngestionProvider):
    """Derive binary flood-onset proxy from rainfall features (not official extents)."""

    provider_id = "flood_events_precip_proxy"
    source_name = "Precipitation-threshold flood-onset proxy"
    license_note = "Derived product — not an official flood catalog"

    def ingest(
        self,
        *,
        features_parquet: str,
        rain_24h_threshold_mm: float = 80.0,
        rain_72h_threshold_mm: float = 150.0,
        horizon_hours: int = 24,
        city_id: Optional[str] = None,
    ) -> IngestResult:
        path = Path(features_parquet)
        if not path.exists():
            return IngestResult(
                success=False,
                provider_id=self.provider_id,
                message=f"Features parquet not found: {features_parquet}",
            )

        df = pd.read_parquet(path)
        required = {"time", "rain_24h", "rain_72h"}
        if not required.issubset(df.columns):
            return IngestResult(
                success=False,
                provider_id=self.provider_id,
                message=f"Features missing columns {required - set(df.columns)}",
            )

        # Label at time t: whether a "qualifying flood onset proxy" occurs within
        # the next horizon_hours. Onset = first hour where thresholds crossed
        # after a quiet period. NEVER use future precip as a feature — only as label.
        df = df.sort_values("time").reset_index(drop=True)
        extreme = (
            (df["rain_24h"] >= rain_24h_threshold_mm)
            | (df["rain_72h"] >= rain_72h_threshold_mm)
        )
        # Onset: extreme True and previous False
        onset = extreme & (~extreme.shift(1, fill_value=False))
        # Forward-looking label: any onset in (t, t+horizon]
        # Use nullable boolean dtype so missing feature windows stay NA (never zero-filled).
        n = len(df)
        onset_idx = set(df.index[onset].tolist())
        label_vals: list[Optional[bool]] = []
        for i in range(n):
            if pd.isna(df.loc[i, "rain_24h"]) or pd.isna(df.loc[i, "rain_72h"]):
                label_vals.append(None)
            else:
                future = any(i < j <= i + horizon_hours for j in onset_idx)
                label_vals.append(bool(future))
        label = pd.Series(label_vals, index=df.index, dtype="boolean")

        out = df[["time"]].copy()
        out["flood_onset_within_horizon"] = label
        out["horizon_hours"] = horizon_hours
        out["label_kind"] = "estimated_proxy"
        out["city_id"] = city_id

        out_path = (
            self.lake.provider_processed(self.provider_id)
            / f"{city_id or 'point'}_h{horizon_hours}_labels.parquet"
        )
        out.to_parquet(out_path, index=False)

        pos = int(out["flood_onset_within_horizon"].fillna(False).sum())
        usable = int(out["flood_onset_within_horizon"].notna().sum())

        return IngestResult(
            success=True,
            provider_id=self.provider_id,
            message=(
                "Built precipitation-proxy flood-onset labels. "
                "These are NOT official flood extents or verified events."
            ),
            processed_path=str(out_path),
            provenance=ProvenanceRecord(
                provider_id=self.provider_id,
                source_name=self.source_name,
                license_note=self.license_note,
                retrieval_url=None,
                retrieved_at=utcnow().isoformat(),
                geographic_coverage={"city_id": city_id},
                temporal_coverage={
                    "start": str(df["time"].min()),
                    "end": str(df["time"].max()),
                },
                quality_limitations=[
                    "Proxy from rainfall thresholds only — high false-alarm risk.",
                    "Not calibrated to local flood authority criteria.",
                    GFD_BLOCKER,
                ],
                observation_kind="estimated",
                extra={
                    "rain_24h_threshold_mm": rain_24h_threshold_mm,
                    "rain_72h_threshold_mm": rain_72h_threshold_mm,
                    "horizon_hours": horizon_hours,
                },
            ),
            stats={"rows": n, "usable_labels": usable, "positive_labels": pos},
            blocker=None if pos > 0 else (
                "Zero positive proxy events in window — model training may be unavailable. "
                "Lower thresholds or widen date range, or supply official event labels."
            ),
        )


class ExternalFloodEventsProvider(IngestionProvider):
    """Load user-supplied GeoJSON/CSV flood events (e.g. after EE export or GFID extract)."""

    provider_id = "flood_events_external"
    source_name = "User-supplied flood event labels"
    license_note = "Inherited from upstream file; caller must document license"

    def ingest(self, *, path: str, city_id: Optional[str] = None) -> IngestResult:
        p = Path(path)
        if not p.exists():
            # Also check default drop folder
            drop = self.lake.provider_raw("flood_events")
            drop.mkdir(parents=True, exist_ok=True)
            return IngestResult(
                success=False,
                provider_id=self.provider_id,
                message=f"File not found: {path}. Place exports in {drop}",
                blocker=GFD_BLOCKER,
            )

        if p.suffix.lower() in {".csv"}:
            df = pd.read_csv(p)
        elif p.suffix.lower() in {".json", ".geojson"}:
            # Minimal: expect properties with event_start
            import json

            raw = json.loads(p.read_text(encoding="utf-8"))
            rows = []
            for feat in raw.get("features", [raw] if "event_start" in raw else []):
                props = feat.get("properties", feat)
                rows.append(props)
            df = pd.DataFrame(rows)
        else:
            return IngestResult(
                success=False,
                provider_id=self.provider_id,
                message="Supported formats: .csv, .json, .geojson",
            )

        out_path = self.lake.provider_processed(self.provider_id) / f"{city_id or 'custom'}_events.parquet"
        df.to_parquet(out_path, index=False)
        return IngestResult(
            success=True,
            provider_id=self.provider_id,
            message=f"Loaded {len(df)} external flood event records.",
            processed_path=str(out_path),
            provenance=ProvenanceRecord(
                provider_id=self.provider_id,
                source_name=self.source_name,
                license_note=self.license_note,
                retrieval_url=str(p),
                retrieved_at=utcnow().isoformat(),
                geographic_coverage={"city_id": city_id},
                quality_limitations=["Caller must verify event date/geo precision before training."],
                observation_kind="observed",
            ),
            stats={"rows": len(df)},
        )

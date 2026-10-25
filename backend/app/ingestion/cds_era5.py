"""CDS ERA5 provider scaffold — requires user CDS credentials (never fabricated)."""

from __future__ import annotations

import os
from typing import Any, Optional

from app.ingestion.base import DataLake, IngestResult, IngestionProvider, ProvenanceRecord, utcnow


CDS_BLOCKER = (
    "CDS ERA5 download requires a Copernicus Climate Data Store account, "
    "acceptance of the ERA5 dataset terms, and credentials. Set environment "
    "variables CDSAPI_URL (default https://cds.climate.copernicus.eu/api) and "
    "CDSAPI_KEY (format: <uid>:<api-key>), then install `cdsapi` and re-run "
    "POST /api/ingest/weather/era5. Until then, use Open-Meteo "
    "(POST /api/ingest/weather/open-meteo) for precipitation features."
)


class CdsEra5Provider(IngestionProvider):
    provider_id = "cds_era5_single_levels"
    source_name = "ERA5 single levels (Copernicus CDS)"
    license_note = "Copernicus CDS licence — user must accept dataset terms on CDS portal"

    def ingest(
        self,
        *,
        west: float,
        south: float,
        east: float,
        north: float,
        year: int,
        month: int,
        day: Optional[int] = None,
        variables: Optional[list[str]] = None,
        **_: Any,
    ) -> IngestResult:
        variables = variables or ["total_precipitation"]
        # Refuse huge variable lists
        allowed = {
            "total_precipitation",
            "volumetric_soil_water_layer_1",
            "runoff",
        }
        bad = [v for v in variables if v not in allowed]
        if bad:
            return IngestResult(
                success=False,
                provider_id=self.provider_id,
                message=f"Unsupported ERA5 variables for this prototype: {bad}. Allowed: {sorted(allowed)}",
            )

        key = os.environ.get("CDSAPI_KEY", "").strip()
        if not key:
            # Write a request stub so the user can see the exact intended request
            stub = {
                "dataset": "reanalysis-era5-single-levels",
                "product_type": "reanalysis",
                "variable": variables,
                "year": str(year),
                "month": f"{month:02d}",
                "day": [f"{day:02d}"] if day else [f"{d:02d}" for d in range(1, 29)],
                "time": [f"{h:02d}:00" for h in range(0, 24)],
                "area": [north, west, south, east],  # CDS N/W/S/E
                "format": "netcdf",
            }
            stub_path = self.lake.provider_raw(self.provider_id) / "pending_request.json"
            self.lake.write_json(stub_path, stub)
            return IngestResult(
                success=False,
                provider_id=self.provider_id,
                message="CDS credentials not configured.",
                raw_path=str(stub_path),
                blocker=CDS_BLOCKER,
                provenance=ProvenanceRecord(
                    provider_id=self.provider_id,
                    source_name=self.source_name,
                    license_note=self.license_note,
                    retrieval_url="https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels",
                    retrieved_at=utcnow().isoformat(),
                    geographic_coverage={
                        "west": west,
                        "south": south,
                        "east": east,
                        "north": north,
                    },
                    temporal_coverage={"year": year, "month": month, "day": day},
                    quality_limitations=["Download not executed — credentials missing."],
                    observation_kind="estimated",
                    extra={"request_stub": stub},
                ),
            )

        # Credentials present — attempt cdsapi if installed
        try:
            import cdsapi  # type: ignore
        except ImportError:
            return IngestResult(
                success=False,
                provider_id=self.provider_id,
                message="cdsapi package not installed. pip install cdsapi",
                blocker="Install cdsapi after setting CDSAPI_KEY.",
            )

        out_path = (
            self.lake.provider_raw(self.provider_id)
            / f"era5_{year}{month:02d}_{west}_{south}_{east}_{north}.nc"
        )
        if self.cache_valid(out_path, min_bytes=1000):
            return IngestResult(
                success=True,
                provider_id=self.provider_id,
                message="Reused cached ERA5 NetCDF.",
                raw_path=str(out_path),
                stats={"cached": True},
            )

        client = cdsapi.Client(
            url=os.environ.get("CDSAPI_URL", "https://cds.climate.copernicus.eu/api"),
            key=key,
        )
        request = {
            "product_type": "reanalysis",
            "variable": variables,
            "year": str(year),
            "month": f"{month:02d}",
            "day": [f"{day:02d}"] if day else [f"{d:02d}" for d in range(1, 29)],
            "time": [f"{h:02d}:00" for h in range(0, 24)],
            "area": [north, west, south, east],
            "format": "netcdf",
        }
        try:
            client.retrieve("reanalysis-era5-single-levels", request, str(out_path))
        except Exception as exc:  # noqa: BLE001
            return IngestResult(
                success=False,
                provider_id=self.provider_id,
                message=f"CDS retrieve failed: {type(exc).__name__}",
                blocker=str(exc)[:500],
            )

        return IngestResult(
            success=True,
            provider_id=self.provider_id,
            message="ERA5 NetCDF downloaded.",
            raw_path=str(out_path),
            provenance=ProvenanceRecord(
                provider_id=self.provider_id,
                source_name=self.source_name,
                license_note=self.license_note,
                retrieval_url="https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels",
                retrieved_at=utcnow().isoformat(),
                geographic_coverage={
                    "west": west,
                    "south": south,
                    "east": east,
                    "north": north,
                },
                temporal_coverage={"year": year, "month": month},
                quality_limitations=[
                    "ERA5 is reanalysis, not a forecast product.",
                    "Validate units (precipitation often metres in ERA5).",
                ],
                observation_kind="estimated",
            ),
            stats={"variables": variables},
        )

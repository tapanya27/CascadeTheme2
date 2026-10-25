"""
India Geodata asset manifest — city-scoped downloads only.

Catalog: https://yashveeeeeeer.github.io/india-geodata/
Repo releases: https://github.com/yashveeeeeeer/india-geodata/releases

Kathmandu (Nepal) is out of India Geodata coverage by design.
IMD gridded rainfall and ALOS AW3D30 are marked external (original portals).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AssetSpec:
    key: str
    tag: str
    filename: str
    description: str
    license_note: str
    max_bytes: int  # refuse larger downloads
    required_for: tuple[str, ...]
    # Direct GitHub release URL (tag may contain '/')
    url: Optional[str] = None
    external_portal: Optional[str] = None
    notes: str = ""


_BASE = "https://github.com/yashveeeeeeer/india-geodata/releases/download"


def _url(tag: str, filename: str) -> str:
    # GitHub release tags with '/' must be URL-encoded in the path
    return f"{_BASE}/{tag.replace('/', '%2F')}/{filename}"


# Prefer parquet / geojson under ~80 MB where possible.
ASSETS: dict[str, AssetSpec] = {
    "flood_inventory": AssetSpec(
        key="flood_inventory",
        tag="environment/flood-inventory",
        filename="INDIA_FLOOD_INVENTORY_V3.geojson",
        description="India Flood Inventory v3 — polygons via India Geodata GitHub release",
        license_note="CC-BY-4.0 (HydroSense Lab / Saharia et al. 2021)",
        max_bytes=40_000_000,
        required_for=("labels",),
        url=_url("environment/flood-inventory", "INDIA_FLOOD_INVENTORY_V3.geojson"),
        notes="Prefer Zenodo CSV when GitHub geojson is unreachable.",
    ),
    "flood_inventory_zenodo_csv": AssetSpec(
        key="flood_inventory_zenodo_csv",
        tag="zenodo/11275211",
        filename="India_Flood_Inventory_v3.csv",
        description="IFI-Impacts v3 event table (dates, districts, attributes) — Zenodo 10.5281/zenodo.11275211",
        license_note="CC-BY-4.0 (Saharia et al. / HydroSense Lab)",
        max_bytes=5_000_000,
        required_for=("labels",),
        url="https://zenodo.org/api/records/11275211/files/India_Flood_Inventory_v3.csv/content",
        external_portal="https://zenodo.org/records/11275211",
    ),
    "flood_inventory_district_area": AssetSpec(
        key="flood_inventory_district_area",
        tag="zenodo/11275211",
        filename="District_FloodedArea.csv",
        description="IFI district flooded-area statistics (impacts table — NOT Flood Atlas)",
        license_note="CC-BY-4.0 Zenodo IFI-Impacts",
        max_bytes=1_000_000,
        required_for=("exposure_context",),
        url="https://zenodo.org/api/records/11275211/files/District_FloodedArea.csv/content",
    ),

    "flood_atlas_district_risk": AssetSpec(
        key="flood_atlas_district_risk",
        tag="environment/flood-atlas",
        filename="District_Wise_flood_risk_data.json",
        description="India Flood Atlas — district flood risk (model-derived H08-CaMa-Flood)",
        license_note="See India Geodata / Flood Atlas terms — MODEL-DERIVED, not inventory events",
        max_bytes=5_000_000,
        required_for=("hazard_context",),
        url=_url("environment/flood-atlas", "District_Wise_flood_risk_data.json"),
        notes="Kept separate from Flood Inventory labels.",
    ),
    "flood_atlas_district_frac": AssetSpec(
        key="flood_atlas_district_frac",
        tag="environment/flood-atlas",
        filename="District_Wise_max_flood_area_frac.json",
        description="India Flood Atlas — district max flood area fraction",
        license_note="Model-derived — not event labels",
        max_bytes=2_000_000,
        required_for=("hazard_context",),
        url=_url("environment/flood-atlas", "District_Wise_max_flood_area_frac.json"),
    ),
    "wards_living_atlas": AssetSpec(
        key="wards_living_atlas",
        tag="urban/boundaries",
        filename="LivingAtlas_Wards.parquet",
        description="Municipal ward polygons (Living Atlas / SBM-related collection)",
        license_note="See India Geodata urban/boundaries release",
        max_bytes=15_000_000,
        required_for=("aggregation",),
        url=_url("urban/boundaries", "LivingAtlas_Wards.parquet"),
    ),
    "slums_mumbai": AssetSpec(
        key="slums_mumbai",
        tag="urban/boundaries",
        filename="UMD_Mumbai_Slum_Boundaries_2016.parquet",
        description="Mumbai slum boundaries 2016 (UMD)",
        license_note="See India Geodata urban/boundaries",
        max_bytes=3_000_000,
        required_for=("vulnerability",),
        url=_url("urban/boundaries", "UMD_Mumbai_Slum_Boundaries_2016.parquet"),
    ),
    "slums_tamil_nadu": AssetSpec(
        key="slums_tamil_nadu",
        tag="urban/boundaries",
        filename="TNGIS_TN_Slum_Boundaries.parquet",
        description="Tamil Nadu slum boundaries (covers Chennai when clipped)",
        license_note="See India Geodata urban/boundaries",
        max_bytes=3_000_000,
        required_for=("vulnerability",),
        url=_url("urban/boundaries", "TNGIS_TN_Slum_Boundaries.parquet"),
    ),
    "healthcare_facilities": AssetSpec(
        key="healthcare_facilities",
        tag="healthcare/facilities",
        filename="INDIA_HEALTH_FACILITIES_NIC.geojson",
        description="NIC India health facilities points (PHC/CHC/hospitals)",
        license_note="See India Geodata healthcare/facilities release",
        max_bytes=80_000_000,
        required_for=("access",),
        url=_url("healthcare/facilities", "INDIA_HEALTH_FACILITIES_NIC.geojson"),
    ),
    "worldpop_ind_1km": AssetSpec(
        key="worldpop_ind_1km",
        tag="external/worldpop",
        filename="ind_pd_2020_1km.tif",
        description="WorldPop India population density 2020 1km (unconstrained)",
        license_note="CC BY 4.0 WorldPop / WP00674",
        max_bytes=40_000_000,
        required_for=("exposure",),
        url=(
            "https://data.worldpop.org/GIS/Population_Density/"
            "Global_2000_2020_1km/2020/IND/ind_pd_2020_1km.tif"
        ),
        external_portal="https://hub.worldpop.org/geodata/summary?id=41746",
    ),
}

# External portals (not auto-downloaded when auth/terms block)
EXTERNAL_PORTALS = {
    "imd_gridded_rainfall": {
        "description": "IMD 0.25° gridded daily rainfall",
        "portal": "https://www.imdpune.gov.in/Clim_Pred_LRF_New/Grided_Data_Download.html",
        "fallback": "Open-Meteo archive (CC BY 4.0) used when IMD portal unreachable; labelled non-IMD",
    },
    "alos_aw3d30": {
        "description": "ALOS AW3D30 30m DEM (JAXA)",
        "portal": "https://www.eorc.jaxa.jp/ALOS/en/dataset/aw3d30/aw3d30_e.htm",
        "fallback": "Open-Meteo elevation / OpenTopoData SRTM for city centroids when AW3D30 tiles unavailable",
    },
    "rivers_streams": {
        "description": "Rivers & Streams (WRIS / SOI) via India Geodata water releases",
        "portal": "https://github.com/yashveeeeeeer/india-geodata/releases",
        "notes": "Full national river network is multi-GB; city AOI clip required after download of smallest usable layer",
    },
    "nic_soi_roads": {
        "description": "NIC / SOI roads via India Geodata infrastructure releases",
        "portal": "https://github.com/yashveeeeeeer/india-geodata/releases",
        "notes": "National road layers are large; prefer city-clipped extracts or OSM already in app when release exceeds budget",
    },
}

INDIA_STUDY_CITIES = ("nagpur", "mumbai", "chennai", "guwahati")
KATHMANDU_NOTE = (
    "Kathmandu is in Nepal. India Geodata (and India Flood Inventory / Flood Atlas / "
    "IMD / NIC / SOI) do not cover it. Keep Kathmandu on Open-Meteo + OSM / demo paths only."
)

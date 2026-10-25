# Data Source Manifest

Raw downloads: `backend/data/raw/<provider>/`  
Processed: `backend/data/processed/<provider>/`  
Models: `backend/data/models/`

| Provider ID | Source | License / terms | Access | Variables / content | Geographic scope | Status |
|-------------|--------|-----------------|--------|---------------------|------------------|--------|
| `open_meteo_archive` | https://open-meteo.com/en/docs/historical-weather-api | CC BY 4.0 (attribution) | Public, no key | hourly precipitation, optional soil_moisture | City centroid or bbox sample points | **ACTIVE** |
| `cds_era5_single_levels` | Copernicus CDS ERA5 | CDS licence; user must accept | Requires CDSAPI credentials | total_precipitation (scaffold) | User bbox | **BLOCKED** until credentials |
| `osm_overpass` | OpenStreetMap via Overpass | ODbL | Public | hospitals, clinics, emergency, major roads, waterways | Selected city bbox | **ACTIVE** |
| `disaster_response_messages` | https://github.com/rmunro/disaster_response_messages | See upstream repo | Public GitHub | multi-label disaster messages | Global text (not live feed) | **ACTIVE** |
| `flood_events_precip_proxy` | Derived from Open-Meteo + threshold rules | Same as weather + model assumption | Local | Binary flood-onset proxy labels | Selected city | **ACTIVE** (proxy — not official flood extents) |
| `gfd_modis` | Global Flood Database (Earth Engine) | See GEE catalog | Requires EE auth | Flood extents | Global | **BLOCKED** |
| `gfid` | Global Flood Impacts Database | See data.gov | Investigate CSV/API | Event impacts | Global | **HOOK** — download when URL stable |
| `worldpop` | worldpop.org | WorldPop terms | Large rasters | Population density | City AOI | **DEFERRED** — zone `population` property supported |
| `imd_rainfall` | IMD / LWCC | Government terms | Often restricted | Station rainfall | India | **BLOCKED** |
| `nwdp` | National Water Data Portal | Government terms | Auth/terms | Hydrology | India | **BLOCKED** |
| `synthetic_demo` | Local generator | Demo only | Local | Zones, hazards, infra | Any city seed | **ACTIVE** (`is_synthetic=true`) |
| `hardcoded_demo_v1` | `backend/app/data/hardcoded_dataset.py` | Demo only | Embedded in repo | 50 zones × 5 cities + infra/hazards/deps/reports | Nagpur, Mumbai, Chennai, Guwahati, Kathmandu | **ACTIVE** (invented/simulated; seed via `/api/data/synthetic/seed`) |
| `india_flood_inventory_v3` | India Geodata / Zenodo IFI (Saharia et al.) | CC-BY-4.0 | Cached under `data/raw/india_geodata/` | Historical flood polygons + event table | India study cities (not Kathmandu) | **ACTIVE** — labels via bbox∩polygon; see `docs/INDIA_GEODATA_INTEGRATION_REPORT.md` |
| `india_flood_atlas` | India Geodata Flood Atlas JSON | See catalog | Cached | Model-derived district flood risk/fraction | India districts | **ACTIVE as context only** — never used as event labels |
| `worldpop_ind_pd_2020_1km` | WorldPop | CC BY 4.0 | `ind_pd_2020_1km.tif` (~17 MB) | Population density | India (sampled at zones) | **ACTIVE** |
| `nic_health_facilities` | India Geodata healthcare release | See catalog | NIC GeoJSON (~47 MB) | Facility points | City AOI clips | **ACTIVE** |
| `imd_gridded_rainfall` | IMD Pune | Government terms | External portal | 0.25° daily rain | India | **BLOCKED** — Open-Meteo used as labelled fallback for EW features |
| `alos_aw3d30` | JAXA | JAXA terms | External portal | 30 m DEM | India tiles | **BLOCKED** this host / not auto-downloaded |
| `zone_vulnerability` | Open-Meteo + OSM Overpass analysis grids | Open-Meteo CC BY 4.0; OSM ODbL; grids project-derived | Local pipeline `/api/ml/dataset/build` | Zone features for hybrid scoring / Isolation Forest | 5 registry cities | **ACTIVE** (OSM fields null when Overpass unreachable) |

## Provenance rules
- Every ingest records: source, version/tag, license note, retrieved_at, bbox/date_range, quality limitations.
- Missing observations are never coerced to zero in scoring features.
- Observation kinds: `observed` | `estimated` | `simulated` | `unverified`.

"""Feature catalog: source, units, missingness policy, geographic resolution.

Never invent observations. Missing values stay null in exports; consumers must
not silently coerce null → 0 for scoring inputs.
"""

from __future__ import annotations

from typing import Any

FEATURE_CATALOG: dict[str, dict[str, Any]] = {
    "city": {
        "units": "categorical",
        "source": "app.cities.registry",
        "resolution": "city",
        "missingness": "never_missing",
        "observation_kind": "observed",
    },
    "zone_id": {
        "units": "id",
        "source": "analysis_grid or PostGIS zones",
        "resolution": "zone",
        "missingness": "never_missing",
        "observation_kind": "estimated",
        "notes": "Analysis-grid cells are not official administrative wards.",
    },
    "latitude": {
        "units": "degrees",
        "source": "zone centroid",
        "resolution": "zone",
        "missingness": "never_missing",
        "observation_kind": "estimated",
    },
    "longitude": {
        "units": "degrees",
        "source": "zone centroid",
        "resolution": "zone",
        "missingness": "never_missing",
        "observation_kind": "estimated",
    },
    "population_density": {
        "units": "persons/km^2",
        "source": "zone.properties or unavailable",
        "resolution": "zone",
        "missingness": "null_when_unavailable",
        "observation_kind": "unverified",
        "notes": "Never invented; WorldPop ingest deferred.",
    },
    "road_density": {
        "units": "road_segments_per_km2",
        "source": "OSM Overpass (highway=*)",
        "resolution": "zone bbox sample",
        "missingness": "null_when_overpass_fails",
        "observation_kind": "observed",
    },
    "road_connectivity": {
        "units": "index_0_1",
        "source": "derived from OSM road segment count + degree proxy",
        "resolution": "zone",
        "missingness": "null_when_roads_unavailable",
        "observation_kind": "estimated",
    },
    "nearest_hospital_km": {
        "units": "km_great_circle",
        "source": "OSM amenity=hospital|clinic",
        "resolution": "zone centroid to nearest point",
        "missingness": "null_when_no_facilities_in_city_sample",
        "observation_kind": "observed",
        "notes": "Not network travel time.",
    },
    "transit_accessibility": {
        "units": "count_of_nearby_stops",
        "source": "OSM public_transport / highway=bus_stop / railway=station",
        "resolution": "zone",
        "missingness": "null_when_overpass_fails",
        "observation_kind": "observed",
    },
    "drainage_indicator": {
        "units": "waterway_segment_count",
        "source": "OSM waterway=*",
        "resolution": "zone",
        "missingness": "null_when_overpass_fails",
        "observation_kind": "observed",
        "notes": "Proxy only — not hydraulic capacity.",
    },
    "rainfall_24h_mm": {
        "units": "mm",
        "source": "Open-Meteo Historical API",
        "resolution": "city_centroid_applied_to_zones",
        "missingness": "null_when_api_fails",
        "observation_kind": "estimated",
        "notes": "City-centroid precip assigned to all zones in city (not spatial field).",
    },
    "rainfall_72h_mm": {
        "units": "mm",
        "source": "Open-Meteo Historical API",
        "resolution": "city_centroid_applied_to_zones",
        "missingness": "null_when_api_fails",
        "observation_kind": "estimated",
    },
    "community_incident_count": {
        "units": "count",
        "source": "community_reports table or corpus geo-tagged subset",
        "resolution": "zone",
        "missingness": "0_only_when_table_queried_and_empty",
        "observation_kind": "observed",
        "notes": "Zero means no matching reports in DB, not 'no incidents occurred'.",
    },
    "infrastructure_failure_count": {
        "units": "count",
        "source": "hazard_observations intersecting zone OR null",
        "resolution": "zone",
        "missingness": "null_when_no_hazard_layer",
        "observation_kind": "estimated",
    },
    "facility_count": {
        "units": "count",
        "source": "OSM healthcare amenities in zone",
        "resolution": "zone",
        "missingness": "0_when_overpass_ok_and_empty",
        "observation_kind": "observed",
    },
    "distance_from_city_centroid_km": {
        "units": "km",
        "source": "computed from analysis-grid centroid vs city registry centroid",
        "resolution": "zone",
        "missingness": "never_missing_for_grid",
        "observation_kind": "estimated",
        "notes": "Geometric peri-urban proxy only — not population or hazard intensity.",
    },
    "source_coverage_score": {
        "units": "fraction_0_1",
        "source": "derived",
        "resolution": "zone",
        "missingness": "never_missing",
        "observation_kind": "estimated",
        "notes": "Fraction of core features that are non-null.",
    },
    "data_quality_flag": {
        "units": "categorical",
        "source": "derived",
        "resolution": "zone",
        "missingness": "never_missing",
        "observation_kind": "estimated",
    },
    "is_synthetic": {
        "units": "bool",
        "source": "pipeline flag",
        "resolution": "row",
        "missingness": "never_missing",
        "observation_kind": "observed",
        "notes": "True only for clearly labelled demo rows — never mixed silently.",
    },
    "geometry_kind": {
        "units": "categorical",
        "source": "pipeline",
        "resolution": "zone",
        "missingness": "never_missing",
        "observation_kind": "observed",
        "notes": "analysis_grid | postgis_zone",
    },
}

CORE_NUMERIC_FEATURES = [
    "population_density",
    "road_density",
    "road_connectivity",
    "nearest_hospital_km",
    "transit_accessibility",
    "drainage_indicator",
    "rainfall_24h_mm",
    "rainfall_72h_mm",
    "community_incident_count",
    "infrastructure_failure_count",
    "facility_count",
    "distance_from_city_centroid_km",
    "source_coverage_score",
]

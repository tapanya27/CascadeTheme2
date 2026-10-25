"""
Hardcoded multi-city demonstration dataset — invented records only.

All coordinates, population figures, hazard markers, infrastructure points,
dependency edges, and community reports are deterministically generated for
software demonstration. They are NOT verified census, flood extents, travel
times, or official facility inventories.

Rules:
- Fixed random seed for reproducibility
- City-specific bboxes from the city registry (no Nagpur coords reused elsewhere)
- Every record marked invented / simulated with provenance
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

from app.cities.registry import BUILTIN_CITIES, require_city

DATASET_SEED = 42
ZONES_PER_CITY = 50
SOURCE_ID = "hardcoded_demo_v1"
PROVENANCE_NOTE = (
    "Invented demonstration record. Coordinates and attributes are simulated "
    "for software testing — not verified real-world measurements."
)

# Neighborhood-style name stems per city (cycled / combined for 50 unique names)
_NAME_STEMS: dict[str, list[str]] = {
    "nagpur": [
        "Sitabuldi", "Dharampeth", "Civil Lines", "Sadar", "Itwari",
        "Mahal", "Trimurti Nagar", "Pratap Nagar", "Manewada", "Besa",
        "Hingna Road", "Koradi", "Kamptee", "Wadi", "Kalmeshwar",
        "Nag River Flats", "Ambazari", "Seminary Hills", "Wardha Road",
        "Ajni", "Reshimbagh", "Gandhibagh", "Jaripatka", "Nandanvan",
        "Hudkeshwar",
    ],
    "mumbai": [
        "Colaba", "Fort", "Dadar", "Bandra", "Andheri",
        "Kurla", "Chembur", "Powai", "Goregaon", "Malad",
        "Borivali", "Thane Creek", "Worli", "Parel", "Byculla",
        "Mahim", "Santacruz", "Vikhroli", "Ghatkopar", "Mulund",
        "Juhu", "Versova", "Dharavi Flats", "Sion", "Trombay",
    ],
    "chennai": [
        "T Nagar", "Mylapore", "Adyar", "Velachery", "Guindy",
        "Tambaram", "Anna Nagar", "Kodambakkam", "Egmore", "Royapuram",
        "Triplicane", "Nungambakkam", "Perambur", "Saidapet", "Porur",
        "Sholinganallur", "Madipakkam", "Pallikaranai", "Ambattur", "Avadi",
        "Besant Nagar", "Thiruvanmiyur", "Kotturpuram", "Kilpauk", "Washermanpet",
    ],
    "guwahati": [
        "Pan Bazaar", "Fancy Bazaar", "Paltan Bazaar", "Chandmari", "Zoo Road",
        "Dispur", "Beltola", "Basistha", "Six Mile", "Ganeshguri",
        "Maligaon", "Jalukbari", "Azara", "Narengi", "Noonmati",
        "Uzan Bazar", "Rehabari", "Lachit Nagar", "GS Road", "Kahilipara",
        "Hengrabari", "Satgaon", "Bharalumukh", "Ulubari", "Hatigaon",
    ],
    "kathmandu": [
        "Thamel", "Durbar Square", "Patan", "Bhaktapur Edge", "Balaju",
        "Kalanki", "Koteshwor", "Baneshwor", "Maharajgunj", "Lazimpat",
        "Boudha", "Chabahil", "Kirtipur", "Swayambhu", "Gongabu",
        "Tokha", "Budhanilkantha", "Jawalakhel", "Kupondole", "Satdobato",
        "Lagankhel", "Imadol", "Balkumari", "Kalimati", "Teku",
    ],
}

_CODE_PREFIX: dict[str, str] = {
    "nagpur": "NAG",
    "mumbai": "MUM",
    "chennai": "CHE",
    "guwahati": "GUW",
    "kathmandu": "KTM",
}

_REPORT_TEMPLATES: list[tuple[str, list[str]]] = [
    ("flooding", [
        "Street flooding after heavy rain near {zone}; knee-deep water on the main lane.",
        "Waterlogging reported around {zone} market; drains overflowing.",
        "Riverbank overflow affecting low-lying homes in {zone}.",
    ]),
    ("blocked_roads", [
        "Main access road to {zone} blocked by debris after overnight rain.",
        "Secondary route near {zone} impassable for ambulances.",
        "Bridge approach to {zone} partially closed; detours congested.",
    ]),
    ("medical_needs", [
        "Clinic in {zone} short on first-aid supplies after local flooding.",
        "Residents in {zone} report delayed ambulance response overnight.",
        "Temporary medical help requested near {zone} shelter.",
    ]),
    ("electricity", [
        "Power outage lasting several hours across parts of {zone}.",
        "Transformer fault near {zone}; backup generators limited.",
    ]),
    ("water", [
        "Contaminated drinking water concerns raised by {zone} residents.",
        "Municipal water supply intermittent in {zone} after flood pulse.",
    ]),
    ("shelter", [
        "Community hall in {zone} opened as temporary shelter; capacity tight.",
        "Evacuation support requested for elderly households in {zone}.",
    ]),
    ("infrastructure_damage", [
        "Retaining wall crack reported along embankment near {zone}.",
        "Local drainage channel damaged beside {zone} arterial road.",
    ]),
]


def list_hardcoded_city_ids() -> list[str]:
    return sorted(_CODE_PREFIX.keys())


class _DetRand:
    """Tiny deterministic PRNG (xorshift64*) — avoids global random state."""

    def __init__(self, seed: int) -> None:
        self._state = seed & 0xFFFFFFFFFFFFFFFF or 1

    def random(self) -> float:
        x = self._state
        x ^= (x >> 12) & 0xFFFFFFFFFFFFFFFF
        x ^= (x << 25) & 0xFFFFFFFFFFFFFFFF
        x ^= (x >> 27) & 0xFFFFFFFFFFFFFFFF
        self._state = x & 0xFFFFFFFFFFFFFFFF
        return ((x * 0x2545F4914F6CDD1D) & 0xFFFFFFFFFFFFFFFF) / 2**64

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self.random()

    def randint(self, a: int, b: int) -> int:
        return a + int(self.random() * (b - a + 1)) % (b - a + 1)

    def choice(self, seq: list[Any]) -> Any:
        return seq[self.randint(0, len(seq) - 1)]

    def gauss(self, mu: float, sigma: float) -> float:
        # Box-Muller
        u1 = max(self.random(), 1e-12)
        u2 = self.random()
        z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2 * math.pi * u2)
        return mu + sigma * z


def _rng(city_id: str, salt: str = "") -> _DetRand:
    material = f"{DATASET_SEED}:{city_id}:{salt}".encode()
    seed_int = int(hashlib.sha256(material).hexdigest()[:16], 16)
    return _DetRand(seed_int)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _zone_grid_cell(
    city_id: str, index: int, cols: int = 10, rows: int = 5
) -> tuple[float, float, float, float, float, float]:
    """Return (minx, miny, maxx, maxy, lon, lat) inside city bbox with jitter."""
    city = require_city(city_id)
    west, south, east, north = city.bbox
    rng = _rng(city_id, f"cell:{index}")
    col = index % cols
    row = index // cols
    cell_w = (east - west) / cols
    cell_h = (north - south) / rows
    # Shrink cell slightly so zones don't overlap heavily
    pad_x = cell_w * 0.12
    pad_y = cell_h * 0.12
    minx = west + col * cell_w + pad_x
    maxx = west + (col + 1) * cell_w - pad_x
    miny = south + row * cell_h + pad_y
    maxy = south + (row + 1) * cell_h - pad_y
    # Small jitter so layouts aren't a perfect checkerboard
    jx = rng.uniform(-cell_w * 0.05, cell_w * 0.05)
    jy = rng.uniform(-cell_h * 0.05, cell_h * 0.05)
    minx, maxx = minx + jx, maxx + jx
    miny, maxy = miny + jy, maxy + jy
    # Keep inside bbox
    minx = _clamp(minx, west, east - 1e-5)
    maxx = _clamp(maxx, minx + 1e-5, east)
    miny = _clamp(miny, south, north - 1e-5)
    maxy = _clamp(maxy, miny + 1e-5, north)
    lon = (minx + maxx) / 2
    lat = (miny + maxy) / 2
    return minx, miny, maxx, maxy, lon, lat


def _zone_name(city_id: str, index: int) -> str:
    stems = _NAME_STEMS[city_id]
    stem = stems[index % len(stems)]
    band = index // len(stems)
    suffix = ["Core", "East", "West", "North", "South", "Extension"][band % 6]
    if band == 0:
        return f"{stem} (demo)"
    return f"{stem} {suffix} (demo)"


def _legacy_nagpur_zone(index: int) -> dict[str, Any] | None:
    """Preserve original NAG-SYN-01..04 codes/bboxes for backward-compatible tests."""
    legacy = [
        ("NAG-SYN-01", "Sitabuldi Core (synthetic)", 79.07, 21.14, 79.10, 21.16),
        ("NAG-SYN-02", "Nag River Corridor (synthetic)", 79.08, 21.12, 79.12, 21.15),
        ("NAG-SYN-03", "Eastern Peri-urban (synthetic)", 79.12, 21.13, 79.16, 21.17),
        ("NAG-SYN-04", "Western Low-lying (synthetic)", 79.02, 21.13, 79.07, 21.17),
    ]
    if index >= len(legacy):
        return None
    code, name, minx, miny, maxx, maxy = legacy[index]
    lon = (minx + maxx) / 2
    lat = (miny + maxy) / 2
    return {
        "code": code,
        "name": name,
        "minx": minx,
        "miny": miny,
        "maxx": maxx,
        "maxy": maxy,
        "lon": lon,
        "lat": lat,
    }


def generate_zones(city_id: str, n: int = ZONES_PER_CITY) -> list[dict[str, Any]]:
    city_id = city_id.strip().lower()
    require_city(city_id)
    prefix = _CODE_PREFIX[city_id]
    zones: list[dict[str, Any]] = []
    for i in range(n):
        rng = _rng(city_id, f"zone:{i}")
        legacy = _legacy_nagpur_zone(i) if city_id == "nagpur" else None
        if legacy:
            code = legacy["code"]
            name = legacy["name"]
            minx, miny, maxx, maxy = (
                legacy["minx"],
                legacy["miny"],
                legacy["maxx"],
                legacy["maxy"],
            )
            lon, lat = legacy["lon"], legacy["lat"]
        else:
            # For Nagpur indices 4+, use NAG-Z05..; others MUM-Z01..
            code_idx = i + 1
            code = f"{prefix}-Z{code_idx:02d}"
            name = _zone_name(city_id, i)
            minx, miny, maxx, maxy, lon, lat = _zone_grid_cell(city_id, i)

        # City-flavoured base distributions
        flood_bias = {
            "nagpur": 0.45,
            "mumbai": 0.62,
            "chennai": 0.58,
            "guwahati": 0.70,
            "kathmandu": 0.35,
        }[city_id]
        flood_exposure = _clamp(rng.gauss(flood_bias, 0.18), 0.05, 0.98)
        density = _clamp(rng.gauss(12000 if city_id in {"mumbai", "chennai"} else 7000, 3500), 800, 45000)
        area_km2 = max(0.15, (maxx - minx) * (maxy - miny) * 111.0 * 111.0 * math.cos(math.radians(lat)))
        population = int(density * area_km2)
        elderly = _clamp(rng.gauss(0.11, 0.04), 0.03, 0.28)
        children = _clamp(rng.gauss(0.22, 0.05), 0.08, 0.40)
        disability = _clamp(rng.gauss(0.04, 0.015), 0.01, 0.12)
        informal = _clamp(rng.gauss(0.25 + flood_exposure * 0.2, 0.12), 0.02, 0.85)
        road_access = _clamp(1.0 - flood_exposure * 0.4 + rng.uniform(-0.15, 0.15), 0.05, 0.98)
        road_disruption = _clamp(flood_exposure * 0.7 + (1 - road_access) * 0.4 + rng.uniform(-0.1, 0.1), 0.02, 0.99)
        alt_routes = int(_clamp(rng.gauss(3.5 - flood_exposure * 2, 1.2), 0, 8))
        healthcare_min = _clamp(rng.gauss(18 + flood_exposure * 25, 8), 4, 90)
        hospital_access = _clamp(1.0 - healthcare_min / 100.0 + rng.uniform(-0.1, 0.1), 0.05, 0.98)
        ambulance = _clamp(hospital_access * 0.85 + road_access * 0.15 + rng.uniform(-0.08, 0.08), 0.05, 0.98)
        electricity = _clamp(rng.gauss(0.78 - flood_exposure * 0.25, 0.12), 0.2, 0.98)
        backup_power = _clamp(rng.gauss(0.25, 0.15), 0.0, 0.9)
        water_access = _clamp(rng.gauss(0.72 - flood_exposure * 0.2, 0.14), 0.15, 0.98)
        sanitation = _clamp(rng.gauss(0.68 - informal * 0.3, 0.12), 0.1, 0.97)
        shelter_cap = int(_clamp(rng.gauss(120 + population * 0.01, 80), 20, 800))
        evacuation = _clamp(road_access * 0.6 + (1 - informal) * 0.3 + rng.uniform(-0.1, 0.1), 0.05, 0.98)
        infra_avail = _clamp(rng.gauss(0.55, 0.2), 0.05, 0.98)
        completeness = _clamp(0.55 + rng.uniform(0, 0.4), 0.4, 0.95)

        zones.append(
            {
                "code": code,
                "name": name,
                "city_id": city_id,
                "description": (
                    f"Invented community zone for {require_city(city_id).name} "
                    "demonstration. Not an official administrative boundary."
                ),
                "boundary": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [minx, miny],
                            [maxx, miny],
                            [maxx, maxy],
                            [minx, maxy],
                            [minx, miny],
                        ]
                    ],
                },
                "centroid": {"lon": round(lon, 6), "lat": round(lat, 6)},
                "bbox": [round(minx, 6), round(miny, 6), round(maxx, 6), round(maxy, 6)],
                "properties": {
                    "is_invented": True,
                    "is_synthetic": True,
                    "observation_kind": "simulated",
                    "synthetic": True,
                    "city_id": city_id,
                    "latitude": round(lat, 6),
                    "longitude": round(lon, 6),
                    "population": population,
                    "population_estimate": population,
                    "population_is_synthetic": True,
                    "population_density_per_km2": round(density, 1),
                    "area_km2_approx": round(area_km2, 4),
                    "flood_exposure_index": round(flood_exposure, 4),
                    "elderly_share": round(elderly, 4),
                    "children_share": round(children, 4),
                    "disability_share": round(disability, 4),
                    "informal_housing_share": round(informal, 4),
                    "housing_vulnerability_index": round(
                        _clamp(informal * 0.6 + flood_exposure * 0.4, 0, 1), 4
                    ),
                    "road_accessibility_index": round(road_access, 4),
                    "road_disruption_risk": round(road_disruption, 4),
                    "alternate_routes_count": alt_routes,
                    "healthcare_travel_minutes_est": round(healthcare_min, 1),
                    "hospital_accessibility_index": round(hospital_access, 4),
                    "ambulance_access_index": round(ambulance, 4),
                    "electricity_reliability": round(electricity, 4),
                    "backup_power_share": round(backup_power, 4),
                    "water_access_index": round(water_access, 4),
                    "sanitation_index": round(sanitation, 4),
                    "emergency_shelter_capacity": shelter_cap,
                    "evacuation_accessibility": round(evacuation, 4),
                    "infrastructure_availability": round(infra_avail, 4),
                    "data_completeness": round(completeness, 4),
                    "note": "Boundaries and attributes are illustrative only",
                    "provenance": {
                        "source_id": SOURCE_ID,
                        "dataset_seed": DATASET_SEED,
                        "invented": True,
                        "observation_kind": "simulated",
                        "disclaimer": PROVENANCE_NOTE,
                    },
                },
            }
        )
    return zones


def generate_infrastructure(
    city_id: str, zones: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    city_id = city_id.strip().lower()
    rng = _rng(city_id, "infra")
    prefix = _CODE_PREFIX[city_id]
    city = require_city(city_id)
    specs: list[tuple[str, str]] = [
        ("hospital", f"{city.name} Central Hospital (demo)"),
        ("hospital", f"{city.name} District Hospital (demo)"),
        ("clinic", f"{city.name} Community Clinic North (demo)"),
        ("clinic", f"{city.name} Community Clinic South (demo)"),
        ("emergency_facility", f"{city.name} Emergency Hub (demo)"),
        ("emergency_facility", f"{city.name} Relief Staging Point (demo)"),
        ("road", f"{city.name} Arterial Node A (demo)"),
        ("road", f"{city.name} Arterial Node B (demo)"),
        ("road", f"{city.name} Bypass Node (demo)"),
        ("other", f"{city.name} Water Works (demo)"),
        ("other", f"{city.name} Substation (demo)"),
        ("other", f"{city.name} Shelter Complex (demo)"),
    ]
    items: list[dict[str, Any]] = []
    for i, (itype, name) in enumerate(specs):
        # Place near a zone centroid with small offset inside city bbox
        z = zones[i % len(zones)]
        lon = z["centroid"]["lon"] + rng.uniform(-0.008, 0.008)
        lat = z["centroid"]["lat"] + rng.uniform(-0.008, 0.008)
        west, south, east, north = city.bbox
        lon = _clamp(lon, west + 0.001, east - 0.001)
        lat = _clamp(lat, south + 0.001, north - 0.001)
        items.append(
            {
                "external_id": f"{SOURCE_ID}/{prefix}/infra/{i:02d}",
                "name": name,
                "infrastructure_type": itype,
                "city_id": city_id,
                "lon": round(lon, 6),
                "lat": round(lat, 6),
                "zone_code": z["code"],
                "properties": {
                    "is_invented": True,
                    "is_synthetic": True,
                    "observation_kind": "simulated",
                    "synthetic": True,
                    "city_id": city_id,
                    "note": "Location approximate / illustrative",
                    "provenance": {
                        "source_id": SOURCE_ID,
                        "invented": True,
                        "disclaimer": PROVENANCE_NOTE,
                    },
                },
                "notes": "Invented demonstration record — not a verified facility.",
            }
        )
    return items


def generate_hazards(
    city_id: str, zones: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    city_id = city_id.strip().lower()
    rng = _rng(city_id, "hazards")
    # Prefer higher flood-exposure zones
    ranked = sorted(
        zones,
        key=lambda z: float(z["properties"]["flood_exposure_index"]),
        reverse=True,
    )
    severities = ["low", "moderate", "high", "severe", "moderate", "high"]
    htypes = ["flood", "waterlogging", "flood", "waterlogging", "other"]
    items: list[dict[str, Any]] = []
    n = 20
    for i in range(n):
        z = ranked[i % max(1, len(ranked) // 2 + 1)]
        lon = z["centroid"]["lon"] + rng.uniform(-0.006, 0.006)
        lat = z["centroid"]["lat"] + rng.uniform(-0.006, 0.006)
        sev = severities[i % len(severities)]
        htype = htypes[i % len(htypes)]
        items.append(
            {
                "external_id": f"{SOURCE_ID}/{city_id}/hazard/{i:02d}",
                "city_id": city_id,
                "hazard_type": htype,
                "severity": sev,
                "observed_on": f"2024-{(6 + (i % 3)):02d}-{(10 + (i % 18)):02d}",
                "description": (
                    f"Invented {htype} marker near {z['name']} — NOT a verified observation"
                ),
                "lon": round(lon, 6),
                "lat": round(lat, 6),
                "zone_code": z["code"],
                "severity_score": round(
                    {"low": 1.0, "moderate": 2.5, "high": 5.0, "severe": 8.0}.get(sev, 1.5),
                    2,
                ),
                "properties": {
                    "is_invented": True,
                    "is_synthetic": True,
                    "observation_kind": "simulated",
                    "synthetic": True,
                    "city_id": city_id,
                    "linked_zone_code": z["code"],
                    "provenance": {
                        "source_id": SOURCE_ID,
                        "invented": True,
                        "disclaimer": PROVENANCE_NOTE,
                    },
                },
            }
        )
    return items


def generate_dependencies(
    city_id: str, zones: list[dict[str, Any]], infra: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """City-scoped analytical + asset dependency edges (unique triplets)."""
    city_id = city_id.strip().lower()
    prefix = _CODE_PREFIX[city_id]
    edges: list[dict[str, Any]] = [
        {
            "source_node": f"{prefix}:heavy_rainfall",
            "target_node": f"{prefix}:flood_exposure",
            "relationship_type": "may_increase",
            "evidence_kind": "hypothesized",
            "evidence": (
                f"Invented pathway for {city_id}: rainfall may elevate flood exposure."
            ),
            "strength": 0.6,
            "confidence": 0.35,
            "zone_code": None,
            "provenance": {
                "is_invented": True,
                "city_id": city_id,
                "source_id": SOURCE_ID,
                "nature": "hypothesis",
            },
        },
        {
            "source_node": f"{prefix}:flood_exposure",
            "target_node": f"{prefix}:road_disruption",
            "relationship_type": "may_cause",
            "evidence_kind": "assumed",
            "evidence": "Assumed demo link: flood markers near roads inform disruption proxy.",
            "strength": 0.55,
            "confidence": 0.4,
            "zone_code": zones[0]["code"] if zones else None,
            "provenance": {
                "is_invented": True,
                "city_id": city_id,
                "source_id": SOURCE_ID,
                "nature": "model_assumption",
            },
        },
        {
            "source_node": f"{prefix}:road_disruption",
            "target_node": f"{prefix}:hospital_travel_time",
            "relationship_type": "may_increase",
            "evidence_kind": "hypothesized",
            "evidence": "Hypothesized: disrupted roads may increase emergency travel burden.",
            "strength": 0.5,
            "confidence": 0.3,
            "zone_code": None,
            "provenance": {
                "is_invented": True,
                "city_id": city_id,
                "source_id": SOURCE_ID,
            },
        },
    ]
    # Link first hospital + first road to a high-exposure zone
    hospitals = [i for i in infra if i["infrastructure_type"] == "hospital"]
    roads = [i for i in infra if i["infrastructure_type"] == "road"]
    hot = max(zones, key=lambda z: z["properties"]["flood_exposure_index"])
    if hospitals:
        edges.append(
            {
                "source_node": f"{prefix}:infra:{hospitals[0]['external_id']}",
                "target_node": f"{prefix}:zone:{hot['code']}",
                "relationship_type": "serves",
                "evidence_kind": "assumed",
                "evidence": "Assumed service link for cascade demonstration.",
                "strength": 0.7,
                "confidence": 0.45,
                "zone_code": hot["code"],
                "provenance": {
                    "is_invented": True,
                    "city_id": city_id,
                    "source_id": SOURCE_ID,
                },
            }
        )
    if roads:
        edges.append(
            {
                "source_node": f"{prefix}:infra:{roads[0]['external_id']}",
                "target_node": f"{prefix}:zone:{hot['code']}",
                "relationship_type": "access_route_for",
                "evidence_kind": "assumed",
                "evidence": "Assumed access-route link for cascade demonstration.",
                "strength": 0.65,
                "confidence": 0.4,
                "zone_code": hot["code"],
                "provenance": {
                    "is_invented": True,
                    "city_id": city_id,
                    "source_id": SOURCE_ID,
                },
            }
        )
    return edges


def generate_reports(
    city_id: str, zones: list[dict[str, Any]], n: int = 12
) -> list[dict[str, Any]]:
    city_id = city_id.strip().lower()
    rng = _rng(city_id, "reports")
    items: list[dict[str, Any]] = []
    for i in range(n):
        z = zones[rng.randint(0, len(zones) - 1)]
        category, templates = _REPORT_TEMPLATES[i % len(_REPORT_TEMPLATES)]
        text = templates[i % len(templates)].format(zone=z["name"])
        text_hash = hashlib.sha256(f"{city_id}:{i}:{text}".encode()).hexdigest()
        items.append(
            {
                "city_id": city_id,
                "text_redacted": text,
                "text_hash": text_hash,
                "near_duplicate_key": text_hash[:16],
                "disaster_related": True,
                "disaster_related_proba": 0.72,
                "labels": [category],
                "label_probas": {category: 0.68},
                "category": category,
                "needs_human_review": True,
                "reviewed": False,
                "verification_status": "unverified",
                "location_precision": "zone",
                "location": {
                    "city_id": city_id,
                    "zone_code": z["code"],
                    "lat": z["centroid"]["lat"],
                    "lon": z["centroid"]["lon"],
                    "is_invented": True,
                },
                "observation_kind": "simulated",
                "source_reliability": "demo_hardcoded",
                "observed_at": f"2024-07-{(1 + i % 28):02d}T{(8 + i % 12):02d}:00:00+00:00",
                "provenance": {
                    "is_invented": True,
                    "source_id": SOURCE_ID,
                    "dataset_seed": DATASET_SEED,
                    "disclaimer": PROVENANCE_NOTE,
                },
            }
        )
    return items


def build_city_dataset(city_id: str) -> dict[str, Any]:
    city_id = city_id.strip().lower()
    if city_id not in _CODE_PREFIX:
        raise KeyError(
            f"Hardcoded dataset not defined for city_id={city_id!r}. "
            f"Known: {', '.join(sorted(_CODE_PREFIX))}"
        )
    city = require_city(city_id)
    zones = generate_zones(city_id)
    infra = generate_infrastructure(city_id, zones)
    hazards = generate_hazards(city_id, zones)
    deps = generate_dependencies(city_id, zones, infra)
    reports = generate_reports(city_id, zones)
    return {
        "city_id": city_id,
        "city_name": city.name,
        "country": city.country,
        "source_id": SOURCE_ID,
        "dataset_seed": DATASET_SEED,
        "is_invented": True,
        "disclaimer": PROVENANCE_NOTE,
        "zones": zones,
        "infrastructure": infra,
        "hazards": hazards,
        "dependencies": deps,
        "community_reports": reports,
        "counts": {
            "zones": len(zones),
            "infrastructure": len(infra),
            "hazards": len(hazards),
            "dependencies": len(deps),
            "community_reports": len(reports),
        },
    }


def build_full_dataset() -> dict[str, Any]:
    cities = {cid: build_city_dataset(cid) for cid in list_hardcoded_city_ids()}
    total_zones = sum(c["counts"]["zones"] for c in cities.values())
    return {
        "source_id": SOURCE_ID,
        "dataset_seed": DATASET_SEED,
        "is_invented": True,
        "disclaimer": PROVENANCE_NOTE,
        "cities": cities,
        "totals": {
            "cities": len(cities),
            "zones": total_zones,
            "infrastructure": sum(c["counts"]["infrastructure"] for c in cities.values()),
            "hazards": sum(c["counts"]["hazards"] for c in cities.values()),
            "dependencies": sum(c["counts"]["dependencies"] for c in cities.values()),
            "community_reports": sum(
                c["counts"]["community_reports"] for c in cities.values()
            ),
        },
    }


# Sanity: ensure registry cities match hardcoded set
assert set(list_hardcoded_city_ids()) <= set(BUILTIN_CITIES.keys())

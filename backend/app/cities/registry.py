"""City / study-area registry — city-agnostic operation (not Nagpur-locked)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class CityProfile:
    """Geographic study area definition (WGS84 lon/lat)."""

    id: str
    name: str
    country: str
    # west, south, east, north
    bbox: tuple[float, float, float, float]
    centroid: tuple[float, float]  # lon, lat
    timezone: str = "UTC"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["bbox"] = {
            "west": self.bbox[0],
            "south": self.bbox[1],
            "east": self.bbox[2],
            "north": self.bbox[3],
        }
        d["centroid"] = {"lon": self.centroid[0], "lat": self.centroid[1]}
        return d


# Curated starter cities for the flood + healthcare prototype.
# Users can also supply a custom bbox via API without adding a registry entry.
BUILTIN_CITIES: dict[str, CityProfile] = {
    "nagpur": CityProfile(
        id="nagpur",
        name="Nagpur",
        country="IN",
        bbox=(78.95, 21.05, 79.20, 21.25),
        centroid=(79.0882, 21.1458),
        timezone="Asia/Kolkata",
        notes="Original demonstration study area (flood + emergency healthcare).",
    ),
    "mumbai": CityProfile(
        id="mumbai",
        name="Mumbai",
        country="IN",
        bbox=(72.77, 18.89, 72.98, 19.30),
        centroid=(72.8777, 19.0760),
        timezone="Asia/Kolkata",
        notes="Coastal megacity; monsoon flood exposure.",
    ),
    "chennai": CityProfile(
        id="chennai",
        name="Chennai",
        country="IN",
        bbox=(80.16, 12.95, 80.34, 13.20),
        centroid=(80.2707, 13.0827),
        timezone="Asia/Kolkata",
        notes="Historical flood events; flat coastal plain.",
    ),
    "guwahati": CityProfile(
        id="guwahati",
        name="Guwahati",
        country="IN",
        bbox=(91.58, 26.10, 91.85, 26.25),
        centroid=(91.7362, 26.1445),
        timezone="Asia/Kolkata",
        notes="Brahmaputra floodplain context.",
    ),
    "kathmandu": CityProfile(
        id="kathmandu",
        name="Kathmandu",
        country="NP",
        bbox=(85.28, 27.65, 85.45, 27.78),
        centroid=(85.3240, 27.7172),
        timezone="Asia/Kathmandu",
        notes="Included for India+Nepal disaster-report corpus geographic relevance.",
    ),
}


def list_cities() -> list[CityProfile]:
    return sorted(BUILTIN_CITIES.values(), key=lambda c: c.name.lower())


def get_city(city_id: str) -> Optional[CityProfile]:
    return BUILTIN_CITIES.get(city_id.strip().lower())


def require_city(city_id: str) -> CityProfile:
    city = get_city(city_id)
    if city is None:
        known = ", ".join(sorted(BUILTIN_CITIES))
        raise KeyError(f"Unknown city_id={city_id!r}. Known: {known}")
    return city


def resolve_bbox(
    *,
    city_id: Optional[str] = None,
    west: Optional[float] = None,
    south: Optional[float] = None,
    east: Optional[float] = None,
    north: Optional[float] = None,
) -> tuple[tuple[float, float, float, float], Optional[CityProfile]]:
    """Return (bbox, city_or_none). Custom bbox wins when all four coords provided."""
    if None not in (west, south, east, north):
        w, s, e, n = float(west), float(south), float(east), float(north)
        if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
            raise ValueError("Invalid bbox: require -180<=west<east<=180 and -90<=south<north<=90")
        city = get_city(city_id) if city_id else None
        return (w, s, e, n), city
    if city_id:
        city = require_city(city_id)
        return city.bbox, city
    # Backward-compatible default: Nagpur
    city = require_city("nagpur")
    return city.bbox, city

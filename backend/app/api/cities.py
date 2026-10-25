"""City / study-area listing."""

from fastapi import APIRouter, HTTPException, Query

from app.cities.registry import get_city, list_cities
from app.config import get_settings

router = APIRouter(tags=["cities"])


@router.get("/api/cities")
def cities():
    settings = get_settings()
    return {
        "default_city_id": settings.default_city_id,
        "items": [c.to_dict() for c in list_cities()],
        "notes": [
            "APIs accept city_id or a custom west/south/east/north bbox.",
            "Absence of OSM features must not be treated as complete coverage.",
        ],
    }


@router.get("/api/cities/{city_id}")
def city_detail(city_id: str):
    city = get_city(city_id)
    if city is None:
        raise HTTPException(status_code=404, detail=f"Unknown city_id={city_id}")
    return city.to_dict()

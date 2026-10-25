"""FastAPI helpers for requiring a valid city_id on requests."""

from __future__ import annotations

from fastapi import HTTPException, Query

from app.cities.registry import CityProfile, get_city, require_city


def parse_city_id(city_id: str = Query(..., description="Study city id from /api/cities")) -> str:
    try:
        return require_city(city_id).id
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def optional_city_id(
    city_id: str | None = Query(None, description="Optional study city id"),
) -> str | None:
    if city_id is None or city_id.strip() == "":
        return None
    city = get_city(city_id)
    if city is None:
        raise HTTPException(status_code=400, detail=f"Unknown city_id={city_id!r}")
    return city.id


def city_profile(city_id: str) -> CityProfile:
    try:
        return require_city(city_id)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

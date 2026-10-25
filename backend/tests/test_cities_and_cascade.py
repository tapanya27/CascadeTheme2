"""City registry and cascade/resilience smoke tests."""

from app.cities.registry import list_cities, require_city, resolve_bbox
from app.services.resilience_service import _topk_jaccard


def test_builtin_cities_include_multiple():
    cities = list_cities()
    ids = {c.id for c in cities}
    assert "nagpur" in ids
    assert "mumbai" in ids
    assert "chennai" in ids


def test_resolve_custom_bbox():
    bbox, city = resolve_bbox(west=72.0, south=18.0, east=73.0, north=19.0)
    assert bbox[0] == 72.0
    assert city is None or city.id  # may be None for custom


def test_require_city():
    c = require_city("nagpur")
    assert c.centroid[0] > 70


def test_topk_jaccard():
    assert _topk_jaccard(["a", "b", "c"], ["a", "b", "d"], 3) == 0.5

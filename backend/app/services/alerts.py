"""Alert ingest, deduplication, Open-Meteo forecast checks, and labeled demo adapter."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.cities.registry import require_city
from app.models.alert import LiveAlert
from app.models.zone import Zone

logger = logging.getLogger(__name__)

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
# mm in the next 6 hours — soft threshold for a "heavy rainfall outlook" notice
RAIN_THRESHOLD_MM = 25.0
SOURCE_OPEN_METEO = "open_meteo_forecast"
SOURCE_DEMO = "demo_adapter"

ALERT_TYPES = {
    "weather_rainfall",
    "flood_warning",
    "road_closure",
    "infrastructure",
    "community_report",
    "risk_change",
}

SEVERITIES = {"info", "watch", "warning", "urgent"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _valid_coords(lon: Optional[float], lat: Optional[float]) -> bool:
    if lon is None or lat is None:
        return False
    try:
        lon_f, lat_f = float(lon), float(lat)
    except (TypeError, ValueError):
        return False
    return -180.0 <= lon_f <= 180.0 and -90.0 <= lat_f <= 90.0


def serialize_alert(row: LiveAlert) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "city_id": row.city_id,
        "source_name": row.source_name,
        "source_event_id": row.source_event_id,
        "alert_type": row.alert_type,
        "severity": row.severity,
        "title": row.title,
        "description": row.description,
        "lon": row.lon,
        "lat": row.lat,
        "has_reliable_coords": bool(row.has_reliable_coords),
        "zone_id": str(row.zone_id) if row.zone_id else None,
        "zone_code": row.zone_code,
        "area_label": row.area_label,
        "source_url": row.source_url,
        "verification_status": row.verification_status,
        "authenticity": row.authenticity,
        "is_demo": bool(row.is_demo),
        "observed_at": row.observed_at.isoformat() if row.observed_at else None,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "ingested_at": row.ingested_at.isoformat() if row.ingested_at else None,
        "is_read": bool(row.is_read),
        "is_acknowledged": bool(row.is_acknowledged),
        "is_resolved": bool(row.is_resolved),
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "extra": row.extra or {},
        "display_label": "Demo Alert" if row.is_demo else None,
    }


def upsert_alert(
    db: Session,
    *,
    city_id: str,
    source_name: str,
    source_event_id: str,
    alert_type: str,
    severity: str,
    title: str,
    description: str,
    lon: Optional[float] = None,
    lat: Optional[float] = None,
    zone_id: Optional[uuid.UUID] = None,
    zone_code: Optional[str] = None,
    area_label: Optional[str] = None,
    source_url: Optional[str] = None,
    verification_status: str = "unverified",
    authenticity: str = "demo",
    is_demo: bool = False,
    observed_at: Optional[datetime] = None,
    published_at: Optional[datetime] = None,
    extra: Optional[dict[str, Any]] = None,
) -> tuple[LiveAlert, bool]:
    """Insert alert if new. Returns (row, created)."""
    existing = (
        db.query(LiveAlert)
        .filter(
            LiveAlert.source_name == source_name,
            LiveAlert.source_event_id == source_event_id,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing, False

    reliable = _valid_coords(lon, lat)
    row = LiveAlert(
        city_id=city_id,
        source_name=source_name,
        source_event_id=source_event_id,
        alert_type=alert_type if alert_type in ALERT_TYPES else "weather_rainfall",
        severity=severity if severity in SEVERITIES else "info",
        title=title[:512],
        description=description or "",
        lon=float(lon) if reliable else None,
        lat=float(lat) if reliable else None,
        has_reliable_coords=reliable,
        zone_id=zone_id,
        zone_code=zone_code,
        area_label=area_label,
        source_url=source_url,
        verification_status=verification_status,
        authenticity=authenticity,
        is_demo=is_demo,
        observed_at=observed_at,
        published_at=published_at or _utcnow(),
        ingested_at=_utcnow(),
        extra=extra or {},
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
        return row, True
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(LiveAlert)
            .filter(
                LiveAlert.source_name == source_name,
                LiveAlert.source_event_id == source_event_id,
            )
            .one()
        )
        return existing, False


def list_alerts(
    db: Session,
    city_id: str,
    *,
    include_resolved: bool = True,
    limit: int = 50,
) -> list[LiveAlert]:
    q = db.query(LiveAlert).filter(LiveAlert.city_id == city_id)
    if not include_resolved:
        q = q.filter(LiveAlert.is_resolved.is_(False))
    return (
        q.order_by(LiveAlert.ingested_at.desc()).limit(min(max(limit, 1), 200)).all()
    )


def unread_count(db: Session, city_id: str) -> int:
    return (
        db.query(LiveAlert)
        .filter(
            LiveAlert.city_id == city_id,
            LiveAlert.is_read.is_(False),
            LiveAlert.is_resolved.is_(False),
        )
        .count()
    )


def mark_read(db: Session, alert_id: uuid.UUID, city_id: str) -> Optional[LiveAlert]:
    row = (
        db.query(LiveAlert)
        .filter(LiveAlert.id == alert_id, LiveAlert.city_id == city_id)
        .one_or_none()
    )
    if row is None:
        return None
    row.is_read = True
    db.commit()
    db.refresh(row)
    return row


def mark_all_read(db: Session, city_id: str) -> int:
    rows = (
        db.query(LiveAlert)
        .filter(LiveAlert.city_id == city_id, LiveAlert.is_read.is_(False))
        .all()
    )
    for r in rows:
        r.is_read = True
    db.commit()
    return len(rows)


def acknowledge(db: Session, alert_id: uuid.UUID, city_id: str) -> Optional[LiveAlert]:
    row = (
        db.query(LiveAlert)
        .filter(LiveAlert.id == alert_id, LiveAlert.city_id == city_id)
        .one_or_none()
    )
    if row is None:
        return None
    row.is_acknowledged = True
    row.is_read = True
    db.commit()
    db.refresh(row)
    return row


def resolve(db: Session, alert_id: uuid.UUID, city_id: str) -> Optional[LiveAlert]:
    row = (
        db.query(LiveAlert)
        .filter(LiveAlert.id == alert_id, LiveAlert.city_id == city_id)
        .one_or_none()
    )
    if row is None:
        return None
    row.is_resolved = True
    row.is_read = True
    row.resolved_at = _utcnow()
    db.commit()
    db.refresh(row)
    return row


def _pick_zone_near(db: Session, city_id: str) -> Optional[Zone]:
    return (
        db.query(Zone)
        .filter(Zone.city_id == city_id)
        .order_by(Zone.code.asc())
        .first()
    )


def create_demo_alert(
    db: Session,
    city_id: str,
    *,
    alert_type: str = "weather_rainfall",
    severity: str = "warning",
) -> LiveAlert:
    """Clearly labeled demonstration alert — never presented as official."""
    city = require_city(city_id)
    zone = _pick_zone_near(db, city_id)
    now = _utcnow()
    event_id = f"demo-{city_id}-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    lon, lat = city.centroid
    area = zone.name if zone else city.name
    titles = {
        "weather_rainfall": "Demo: Heavy Rainfall Outlook",
        "flood_warning": "Demo: Flood Watch Example",
        "road_closure": "Demo: Road May Be Hard to Use",
        "infrastructure": "Demo: Essential Service Check",
        "community_report": "Demo: New Community Report",
        "risk_change": "Demo: Area Score Updated",
    }
    descriptions = {
        "weather_rainfall": (
            "This is a demonstration alert so you can practice the map workflow. "
            "It is NOT an official weather warning. Check nearby roads and essential "
            f"services around {area}."
        ),
        "flood_warning": (
            "Example flood-watch style notice for teaching the product. "
            "Not an official flood warning from any authority."
        ),
        "road_closure": (
            "Example notice that a road might be harder to use. "
            "Demonstration only — not a verified closure."
        ),
        "infrastructure": (
            "Example reminder to check access to an essential service. Demonstration only."
        ),
        "community_report": (
            "Example community-style report for the notification workflow. Unverified demo."
        ),
        "risk_change": (
            "Example notice that a scored area changed category. "
            "Demonstration of the alert→map link — not a live model push."
        ),
    }
    row, _ = upsert_alert(
        db,
        city_id=city_id,
        source_name=SOURCE_DEMO,
        source_event_id=event_id,
        alert_type=alert_type if alert_type in ALERT_TYPES else "weather_rainfall",
        severity=severity if severity in SEVERITIES else "warning",
        title=titles.get(alert_type, titles["weather_rainfall"]),
        description=descriptions.get(alert_type, descriptions["weather_rainfall"]),
        lon=lon,
        lat=lat,
        zone_id=zone.id if zone else None,
        zone_code=zone.code if zone else None,
        area_label=area,
        source_url=None,
        verification_status="demo",
        authenticity="demo",
        is_demo=True,
        observed_at=now,
        published_at=now,
        extra={
            "demo": True,
            "label": "Demo Alert",
            "disclaimer": "Example only — not a real incident or official warning.",
        },
    )
    return row


def _http_json(url: str, timeout: float = 20.0) -> dict[str, Any]:
    req = Request(url, headers={"User-Agent": "Critical1Percent/1.0 (hackathon demo)"})
    with urlopen(req, timeout=timeout) as resp:
        import json

        return json.loads(resp.read().decode("utf-8"))


def poll_open_meteo_forecast(db: Session, city_id: str) -> dict[str, Any]:
    """
    Check Open-Meteo public forecast API for elevated short-term rainfall.

    This is a documented free forecast model feed — NOT an official IMD/DHM warning.
    Alerts are labeled authenticity=forecast_model.
    """
    city = require_city(city_id)
    lon, lat = city.centroid
    qs = urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "hourly": "precipitation",
            "forecast_days": 1,
            "timezone": city.timezone,
        }
    )
    url = f"{OPEN_METEO_FORECAST}?{qs}"
    checked_at = _utcnow()
    try:
        data = _http_json(url)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        logger.warning("Open-Meteo poll failed for %s: %s", city_id, type(exc).__name__)
        return {
            "ok": False,
            "source": SOURCE_OPEN_METEO,
            "city_id": city_id,
            "checked_at": checked_at.isoformat(),
            "error": "Could not reach the weather forecast service right now.",
            "created": False,
            "alert": None,
        }

    hourly = data.get("hourly") or {}
    precip = hourly.get("precipitation") or []
    times = hourly.get("time") or []
    window = precip[:6]
    total = float(sum(float(x or 0) for x in window))
    day_key = checked_at.strftime("%Y-%m-%d")
    event_id = f"{city_id}-{day_key}-rain6h"

    result_base = {
        "ok": True,
        "source": SOURCE_OPEN_METEO,
        "city_id": city_id,
        "checked_at": checked_at.isoformat(),
        "precipitation_next_6h_mm": round(total, 2),
        "threshold_mm": RAIN_THRESHOLD_MM,
        "source_url": "https://open-meteo.com/",
        "authenticity_note": (
            "Open-Meteo weather forecast model — not an official government warning."
        ),
    }

    if total < RAIN_THRESHOLD_MM:
        return {
            **result_base,
            "created": False,
            "message": "Forecast checked — no elevated rainfall outlook for this window.",
            "alert": None,
        }

    peak_idx = max(range(len(window)), key=lambda i: float(window[i] or 0), default=0)
    peak_time = times[peak_idx] if peak_idx < len(times) else None
    zone = _pick_zone_near(db, city_id)
    row, created = upsert_alert(
        db,
        city_id=city_id,
        source_name=SOURCE_OPEN_METEO,
        source_event_id=event_id,
        alert_type="weather_rainfall",
        severity="watch" if total < 40 else "warning",
        title="Heavy Rainfall Outlook (Forecast)",
        description=(
            f"Open-Meteo forecast suggests about {total:.0f} mm of rain in the next "
            f"~6 hours near {city.name}. This is a weather-model outlook, not an "
            "official flood warning. Check nearby roads and essential services."
        ),
        lon=lon,
        lat=lat,
        zone_id=zone.id if zone else None,
        zone_code=zone.code if zone else None,
        area_label=city.name,
        source_url="https://open-meteo.com/",
        verification_status="forecast",
        authenticity="forecast_model",
        is_demo=False,
        observed_at=checked_at,
        published_at=checked_at,
        extra={
            "precipitation_next_6h_mm": round(total, 2),
            "peak_hour": peak_time,
            "model": "open-meteo-forecast",
            "not_official_warning": True,
        },
    )
    return {
        **result_base,
        "created": created,
        "message": (
            "New rainfall outlook stored."
            if created
            else "Same daily rainfall outlook already stored (deduplicated)."
        ),
        "alert": serialize_alert(row),
    }


def source_status(db: Session, city_id: str) -> dict[str, Any]:
    """Summarize feed health for the UI — checked vs empty vs failed."""
    latest_om = (
        db.query(LiveAlert)
        .filter(
            LiveAlert.city_id == city_id,
            LiveAlert.source_name == SOURCE_OPEN_METEO,
        )
        .order_by(LiveAlert.ingested_at.desc())
        .first()
    )
    latest_demo = (
        db.query(LiveAlert)
        .filter(
            LiveAlert.city_id == city_id,
            LiveAlert.source_name == SOURCE_DEMO,
        )
        .order_by(LiveAlert.ingested_at.desc())
        .first()
    )
    return {
        "city_id": city_id,
        "sources": [
            {
                "id": SOURCE_OPEN_METEO,
                "label": "Open-Meteo rainfall forecast",
                "kind": "forecast_model",
                "official": False,
                "last_alert_at": (
                    latest_om.ingested_at.isoformat() if latest_om else None
                ),
                "notes": (
                    "Public forecast API. Alerts only when modeled rain exceeds a "
                    "local threshold. Not IMD/DHM official warnings."
                ),
            },
            {
                "id": SOURCE_DEMO,
                "label": "Demo Alert adapter",
                "kind": "demo",
                "official": False,
                "last_alert_at": (
                    latest_demo.ingested_at.isoformat() if latest_demo else None
                ),
                "notes": "Creates clearly labeled example alerts for demos and tests.",
            },
        ],
        "stale_after_hours": 24,
        "generated_at": _utcnow().isoformat(),
    }


def prune_old_demo_alerts(db: Session, older_than_hours: int = 72) -> int:
    cutoff = _utcnow() - timedelta(hours=older_than_hours)
    rows = (
        db.query(LiveAlert)
        .filter(
            LiveAlert.is_demo.is_(True),
            LiveAlert.ingested_at < cutoff,
        )
        .all()
    )
    n = len(rows)
    for r in rows:
        db.delete(r)
    if n:
        db.commit()
    return n

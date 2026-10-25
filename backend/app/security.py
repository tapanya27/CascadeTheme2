"""Request limits, upload guards, and safe error helpers (Module 4)."""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque, Dict

from fastapi import HTTPException, Request, UploadFile

from app.config import get_settings

logger = logging.getLogger(__name__)

_ALLOWED_UPLOAD_SUFFIXES = (".csv", ".geojson", ".json")
_lock = Lock()
_hits: Dict[str, Deque[float]] = defaultdict(deque)


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def check_rate_limit(request: Request, *, expensive: bool = False) -> None:
    settings = get_settings()
    if not expensive:
        return
    key = f"expensive:{client_key(request)}"
    now = time.time()
    window = settings.rate_limit_window_seconds
    limit = settings.rate_limit_expensive_per_window
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            logger.warning("Rate limit exceeded for %s", key)
            raise HTTPException(
                status_code=429,
                detail=(
                    "Too many expensive requests. Wait and retry. "
                    "Imports, assessments, and scenario comparisons are rate-limited."
                ),
            )
        q.append(now)


async def read_upload_limited(file: UploadFile) -> tuple[bytes, str]:
    """Read upload with type + size enforcement. Does not log file contents."""
    settings = get_settings()
    filename = file.filename or "upload"
    lower = filename.lower()
    if not any(lower.endswith(s) for s in _ALLOWED_UPLOAD_SUFFIXES):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Allowed: .csv, .geojson, .json",
        )
    # Content-type is advisory only; extension + parser validation are authoritative
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File exceeds maximum upload size of "
                f"{settings.max_upload_bytes} bytes."
            ),
        )
    if not content:
        raise HTTPException(status_code=400, detail="Empty file upload")
    return content, filename


def safe_public_error(message: str, *, status_code: int = 400) -> HTTPException:
    """Return an HTTPException without embedding secrets or stack traces."""
    return HTTPException(status_code=status_code, detail=message)

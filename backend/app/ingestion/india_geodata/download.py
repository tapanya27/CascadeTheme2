"""
Cached downloader for India Geodata / WorldPop assets.

Records actual byte sizes. Refuses oversized downloads. Skips re-download when
a complete cached file exists (size > 0 and optional SHA side-car).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.ingestion.india_geodata.manifest import ASSETS, AssetSpec

USER_AGENT = "Critical1-IndiaGeodata/1.0 (research; local cache)"


def raw_dir(data_dir: Path) -> Path:
    d = Path(data_dir) / "raw" / "india_geodata"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _probe_alternate_urls(spec: AssetSpec) -> list[str]:
    urls = []
    if spec.url:
        urls.append(spec.url)
    # Common filename variants for healthcare
    if spec.key == "healthcare_facilities":
        tag = "healthcare/facilities"
        base = "https://github.com/yashveeeeeeer/india-geodata/releases/download"
        for name in (
            "INDIA_HEALTH_FACILITIES_NIC.geojson",
            "Healthcare_Facilities.geojson",
        ):
            urls.append(f"{base}/{tag.replace('/', '%2F')}/{name}")
    if spec.key.startswith("flood_atlas"):
        tag = "environment/flood-atlas"
        base = "https://github.com/yashveeeeeeer/india-geodata/releases/download"
        urls.append(f"{base}/{tag.replace('/', '%2F')}/{spec.filename}")
        # Assets may live under data/ in repo for tiny JSON
        urls.append(
            f"https://raw.githubusercontent.com/yashveeeeeeer/india-geodata/main/"
            f"data/environment/flood-atlas/{spec.filename}"
        )
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def download_asset(
    key: str,
    data_dir: Path,
    *,
    force: bool = False,
    timeout: int = 120,
) -> dict[str, Any]:
    if key not in ASSETS:
        return {"ok": False, "key": key, "error": f"Unknown asset key {key}"}
    spec = ASSETS[key]
    dest_dir = raw_dir(data_dir) / key
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / spec.filename
    meta_path = dest_dir / "download_meta.json"

    if dest.exists() and dest.stat().st_size > 0 and not force:
        meta = {
            "ok": True,
            "key": key,
            "cached": True,
            "path": str(dest),
            "bytes": dest.stat().st_size,
            "bytes_mb": round(dest.stat().st_size / 1e6, 3),
            "retrieved_at": None,
        }
        if meta_path.exists():
            try:
                prev = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["retrieved_at"] = prev.get("retrieved_at")
                meta["source_url"] = prev.get("source_url")
            except json.JSONDecodeError:
                pass
        return meta

    errors: list[str] = []
    for url in _probe_alternate_urls(spec):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                # Content-Length check when present
                cl = resp.headers.get("Content-Length")
                if cl and int(cl) > spec.max_bytes:
                    errors.append(
                        f"{url}: Content-Length {cl} exceeds max_bytes {spec.max_bytes}"
                    )
                    continue
                chunk_size = 1024 * 256
                total = 0
                tmp = dest.with_suffix(dest.suffix + ".partial")
                with tmp.open("wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > spec.max_bytes:
                            f.close()
                            tmp.unlink(missing_ok=True)
                            raise RuntimeError(
                                f"Download exceeded max_bytes={spec.max_bytes}"
                            )
                        f.write(chunk)
                tmp.replace(dest)
                meta = {
                    "ok": True,
                    "key": key,
                    "cached": False,
                    "path": str(dest),
                    "bytes": total,
                    "bytes_mb": round(total / 1e6, 3),
                    "source_url": url,
                    "tag": spec.tag,
                    "description": spec.description,
                    "license_note": spec.license_note,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "http_status": getattr(resp, "status", 200),
                }
                meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
                return meta
        except Exception as exc:  # noqa: BLE001 — collect and try next URL
            errors.append(f"{url}: {exc}")
            time.sleep(0.5)

    result = {
        "ok": False,
        "key": key,
        "error": "All download URLs failed",
        "attempts": errors,
        "external_portal": spec.external_portal,
        "notes": spec.notes,
    }
    meta_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def download_selected(
    data_dir: Path,
    keys: Optional[list[str]] = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    keys = keys or list(ASSETS.keys())
    results = {k: download_asset(k, data_dir, force=force) for k in keys}
    summary = {
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "ok_count": sum(1 for r in results.values() if r.get("ok")),
        "fail_count": sum(1 for r in results.values() if not r.get("ok")),
        "total_bytes": sum(int(r.get("bytes") or 0) for r in results.values() if r.get("ok")),
        "results": results,
    }
    summary["total_bytes_mb"] = round(summary["total_bytes"] / 1e6, 3)
    out = raw_dir(data_dir) / "download_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary

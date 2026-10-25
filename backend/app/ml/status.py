"""Unified model / dataset coverage / freshness status."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ingestion.base import DataLake
from app.ml.zone_dataset import PROVIDER_ID


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"error": f"Failed to parse {path.name}"}


def _file_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    st = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "bytes": st.st_size,
        "mtime_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
    }


def collect_ml_status(lake: DataLake) -> dict[str, Any]:
    processed = lake.provider_processed(PROVIDER_ID)
    zones_parquet = processed / "zones_features.parquet"
    build_report = _read_json(processed / "build_report.json")
    catalog = _read_json(processed / "feature_catalog.json")

    models = {
        "zone_isolation_forest": {
            "artifact": _file_info(lake.models / "zone_isolation_forest.joblib"),
            "meta": _read_json(lake.models / "zone_isolation_forest_meta.json"),
        },
        "early_warning_nagpur": {
            "artifact": _file_info(lake.models / "ew_nagpur_h24.joblib"),
            "meta": _read_json(lake.models / "ew_nagpur_h24_meta.json"),
        },
        "report_classifier": {
            "artifact": _file_info(lake.models / "report_clf.joblib"),
            "meta": _read_json(lake.models / "report_clf_meta.json"),
        },
    }
    # Optional supervised benchmarks
    for p in lake.models.glob("ew_bench_*_meta.json"):
        models[p.stem] = {"meta": _read_json(p), "artifact": _file_info(p.with_name(p.name.replace("_meta.json", ".joblib")))}

    emb_cache = lake.models / "embedding_cache"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_lake_root": str(lake.root),
        "dataset": {
            "provider_id": PROVIDER_ID,
            "zones_features": _file_info(zones_parquet),
            "build_report": build_report,
            "catalog_summary": {
                "n_records": (catalog or {}).get("n_records"),
                "n_features": (catalog or {}).get("n_features"),
                "file_bytes_parquet": (catalog or {}).get("file_bytes_parquet"),
            }
            if catalog
            else None,
        },
        "models": models,
        "embeddings": {
            "cache_dir": str(emb_cache),
            "cache_exists": emb_cache.exists(),
            "preferred_model": "intfloat/multilingual-e5-small",
            "fallback": "tfidf",
        },
        "india_geodata": _india_geodata_status(lake),
        "claims": {
            "heuristic_scores": "Transparent configurable vulnerability scores — not trained disaster probabilities.",
            "anomaly": "Isolation Forest ranks unusual feature mixes — not crisis predictions.",
            "supervised_ew": (
                "Precipitation-proxy EW benchmarks remain separate from inventory-label "
                "experimental models under data/models/ew_inventory_*."
            ),
            "inventory_ew": (
                "CatBoost/XGBoost trained on India Flood Inventory (Zenodo IFI) labels are "
                "experimental — not operational flood forecasts. Flood Atlas is never used as labels."
            ),
            "simulations": "Cascade / intervention simulations are hypothetical scenarios.",
        },
    }


def _india_geodata_status(lake: DataLake) -> dict[str, Any]:
    root = lake.root
    processed = root / "processed" / "india_geodata"
    return {
        "download_summary": _read_json(root / "raw" / "india_geodata" / "download_summary.json"),
        "label_summary": _read_json(processed / "labels_zenodo_csv" / "label_summary.json"),
        "train_report": _read_json(root / "models" / "ew_inventory_train_report.json"),
        "zone_features": _file_info(processed / "zone_features_india_geodata.parquet"),
        "catboost": _file_info(root / "models" / "ew_inventory_catboost.cbm"),
        "xgboost": _file_info(root / "models" / "ew_inventory_xgboost.joblib"),
        "kathmandu": "Out of India Geodata coverage — not included in inventory training.",
    }

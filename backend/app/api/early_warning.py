"""Flood early-warning train / predict endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import get_settings
from app.early_warning.train import predict_latest, train_early_warning
from app.ingestion.base import DataLake
from app.security import check_rate_limit

router = APIRouter(tags=["early-warning"])


class TrainRequest(BaseModel):
    city_id: str = "nagpur"
    horizon_hours: int = Field(default=24, ge=1, le=168)
    features_parquet: Optional[str] = None
    labels_parquet: Optional[str] = None
    min_positives: int = 5


@router.post("/api/early-warning/train")
def train(body: TrainRequest, request: Request):
    check_rate_limit(request, expensive=True)
    lake = DataLake(Path(get_settings().data_dir))
    features = body.features_parquet
    labels = body.labels_parquet
    if not features:
        cands = sorted(
            lake.provider_processed("open_meteo_archive").glob(
                f"{body.city_id}_*_features.parquet"
            ),
            key=lambda p: p.stat().st_mtime,
        )
        if not cands:
            raise HTTPException(
                status_code=400,
                detail="No features parquet. Ingest Open-Meteo weather first.",
            )
        features = str(cands[-1])
    if not labels:
        cands = sorted(
            lake.provider_processed("flood_events_precip_proxy").glob(
                f"{body.city_id}_h{body.horizon_hours}_labels.parquet"
            ),
            key=lambda p: p.stat().st_mtime,
        )
        if not cands:
            raise HTTPException(
                status_code=400,
                detail="No label parquet. Run /api/ingest/flood-labels/proxy first.",
            )
        labels = str(cands[-1])

    report = train_early_warning(
        features,
        labels,
        lake.models,
        horizon_hours=body.horizon_hours,
        city_id=body.city_id,
        min_positives=body.min_positives,
    )
    return report.to_dict()


@router.get("/api/early-warning/status")
def status(city_id: str = "nagpur", horizon_hours: int = 24):
    lake = DataLake(Path(get_settings().data_dir))
    stem = f"ew_{city_id}_h{horizon_hours}"
    model = lake.models / f"{stem}.joblib"
    meta = lake.models / f"{stem}_meta.json"
    unavail = lake.models / f"{stem}_unavailable.json"
    if model.exists() and meta.exists():
        import json

        return {
            "status": "trained",
            "model_path": str(model),
            "metadata": json.loads(meta.read_text(encoding="utf-8")),
            "concept": "forecasted_crisis_likelihood_proxy",
            "separation_note": (
                "Separate from community vulnerability scores and data-quality confidence."
            ),
        }
    if unavail.exists():
        import json

        return {
            "status": "unavailable",
            "metadata": json.loads(unavail.read_text(encoding="utf-8")),
        }
    return {
        "status": "not_trained",
        "message": "No model artifact. Train after weather + label ingest.",
    }


@router.get("/api/early-warning/predict")
def predict(city_id: str = "nagpur", horizon_hours: int = 24):
    lake = DataLake(Path(get_settings().data_dir))
    model = lake.models / f"ew_{city_id}_h{horizon_hours}.joblib"
    if not model.exists():
        return {
            "available": False,
            "status": "unavailable",
            "reason": "Model not trained for this city/horizon.",
        }
    feats = sorted(
        lake.provider_processed("open_meteo_archive").glob(
            f"{city_id}_*_features.parquet"
        ),
        key=lambda p: p.stat().st_mtime,
    )
    if not feats:
        return {"available": False, "reason": "No feature parquet for city."}
    return predict_latest(str(model), str(feats[-1]))

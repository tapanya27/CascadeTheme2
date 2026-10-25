"""Hybrid ML intelligence API: dataset, scoring, clusters, embeddings, status."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.ingestion.base import DataLake
from app.ml.clusters import build_vulnerability_clusters
from app.ml.embeddings import ReportEmbedder, persist_cluster_result, redact_pii
from app.ml.explain import explain_zone_row
from app.ml.interventions_rules import recommend_interventions
from app.ml.status import collect_ml_status
from app.ml.vulnerability_models import (
    run_zone_intelligence,
    train_isolation_forest,
    try_train_supervised_benchmark,
)
from app.ml.zone_dataset import (
    PROVIDER_ID,
    build_zone_dataset,
    export_postgis_zone_features,
    load_zone_dataframe,
)
from app.scoring.features import extract_all_zone_features
from app.security import check_rate_limit

router = APIRouter(tags=["ml-intelligence"])


def _lake() -> DataLake:
    return DataLake(Path(get_settings().data_dir))


def _scored_path(lake: DataLake) -> Path:
    return lake.provider_processed(PROVIDER_ID) / "zones_scored.parquet"


def _ensure_scored(lake: DataLake) -> pd.DataFrame:
    path = _scored_path(lake)
    if path.exists():
        return pd.read_parquet(path)
    df = load_zone_dataframe(lake)
    scored = run_zone_intelligence(df, lake.models)
    scored.to_parquet(path, index=False)
    return scored


class DatasetBuildRequest(BaseModel):
    city_ids: Optional[list[str]] = None
    n_side: int = Field(default=8, ge=3, le=20)
    skip_overpass: bool = False


class TrainRequest(BaseModel):
    include_supervised_benchmark: bool = True
    city_id_for_ew: str = "nagpur"
    horizon_hours: int = 24


class ReportEmbedRequest(BaseModel):
    texts: list[str] = Field(default_factory=list, max_length=500)
    n_clusters: Optional[int] = Field(default=None, ge=2, le=32)


class CascadeScenarioRequest(BaseModel):
    zone_id: str
    scenario: str = Field(
        description="road_closure | transit_suspension | power_facility_disruption"
    )
    note: str = (
        "Simulated scenario only — not an observed real-world event."
    )


@router.get("/api/ml/status")
def ml_status():
    return collect_ml_status(_lake())


@router.post("/api/ml/dataset/build")
def ml_dataset_build(body: DatasetBuildRequest, request: Request):
    check_rate_limit(request, expensive=True)
    lake = _lake()
    try:
        result = build_zone_dataset(
            lake,
            city_ids=body.city_ids,
            n_side=body.n_side,
            overpass_url=get_settings().osm_overpass_url,
            skip_overpass=body.skip_overpass or (not get_settings().osm_enabled),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    # Clear scored cache so next score uses new data
    sp = _scored_path(lake)
    if sp.exists():
        sp.unlink()
    return result


@router.post("/api/ml/dataset/export-postgis")
def ml_export_postgis(
    request: Request,
    city_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    check_rate_limit(request, expensive=True)
    features = extract_all_zone_features(db, city_id=city_id)
    return export_postgis_zone_features(features, _lake())


@router.get("/api/ml/zones")
def ml_zones(
    city: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    lake = _lake()
    try:
        scored = _ensure_scored(lake)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    df = scored
    if city:
        df = df[df["city"] == city.strip().lower()]
    if category:
        df = df[df["heuristic_category"] == category.strip().lower()]
    total = int(len(df))
    page = df.iloc[offset : offset + limit]
    records = json.loads(page.to_json(orient="records"))
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": records,
        "score_kind": "transparent_heuristic + isolation_forest",
        "disclaimer": (
            "Scores are heuristic / anomaly rankings — not verified crisis probabilities."
        ),
    }


@router.get("/api/ml/zones/{zone_id}/explanation")
def ml_zone_explanation(zone_id: str):
    lake = _lake()
    try:
        scored = _ensure_scored(lake)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    hit = scored[scored["zone_id"].astype(str) == zone_id]
    if hit.empty:
        raise HTTPException(status_code=404, detail=f"Unknown zone_id={zone_id}")
    row = json.loads(hit.iloc[0].to_json())
    explanation = explain_zone_row(row, models_dir=lake.models)
    explanation["recommended_interventions"] = recommend_interventions(row)
    return explanation


@router.get("/api/ml/clusters")
def ml_clusters(
    city: Optional[str] = None,
    min_category: str = "high",
    eps_km: float = Query(default=3.0, ge=0.5, le=50),
):
    lake = _lake()
    try:
        scored = _ensure_scored(lake)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if city:
        scored = scored[scored["city"] == city.strip().lower()]
    payload = build_vulnerability_clusters(
        scored, min_category=min_category, eps_km=eps_km
    )
    return payload


@router.post("/api/ml/train")
def ml_train(body: TrainRequest, request: Request):
    check_rate_limit(request, expensive=True)
    lake = _lake()
    try:
        df = load_zone_dataframe(lake)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    iso = train_isolation_forest(df, lake.models)
    scored = run_zone_intelligence(df, lake.models)
    scored.to_parquet(_scored_path(lake), index=False)

    supervised: list[dict[str, Any]] = []
    if body.include_supervised_benchmark:
        feats = sorted(
            lake.provider_processed("open_meteo_archive").glob(
                f"{body.city_id_for_ew}_*_features.parquet"
            ),
            key=lambda p: p.stat().st_mtime,
        )
        labels = sorted(
            lake.provider_processed("flood_events_precip_proxy").glob(
                f"{body.city_id_for_ew}_h{body.horizon_hours}_labels.parquet"
            ),
            key=lambda p: p.stat().st_mtime,
        )
        if feats and labels:
            reports = try_train_supervised_benchmark(
                str(feats[-1]),
                str(labels[-1]),
                lake.models,
                city_id=body.city_id_for_ew,
                horizon_hours=body.horizon_hours,
                label_kind="estimated_proxy",
            )
            supervised = [r.to_dict() for r in reports]
        else:
            supervised = [
                {
                    "status": "unavailable",
                    "message": (
                        "No Open-Meteo features/labels for supervised benchmark. "
                        "Isolation Forest + heuristic scoring still trained."
                    ),
                }
            ]

    return {
        "isolation_forest": iso.to_dict(),
        "supervised_benchmarks": supervised,
        "n_zones_scored": int(len(scored)),
        "scored_parquet": str(_scored_path(lake)),
    }


@router.post("/api/ml/reports/embed-cluster")
def ml_report_embed_cluster(body: ReportEmbedRequest, request: Request):
    check_rate_limit(request, expensive=True)
    lake = _lake()
    texts = [redact_pii(t) for t in body.texts if t and t.strip()]
    if not texts:
        # Fall back to seed corpus sample if available
        seed = lake.provider_raw("disaster_response_messages") / "seed_messages.csv"
        if seed.exists():
            import csv

            with seed.open(encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    msg = row.get("message") or row.get("text") or ""
                    if msg.strip():
                        texts.append(redact_pii(msg))
                    if len(texts) >= 80:
                        break
        if not texts:
            raise HTTPException(
                status_code=400,
                detail="No texts provided and no seed corpus available.",
            )

    embedder = ReportEmbedder(lake.models / "embedding_cache")
    result = embedder.cluster_reports(texts, n_clusters=body.n_clusters)
    out = lake.provider_processed("report_embeddings") / "latest_clusters.json"
    persist_cluster_result(result, out)
    payload = result.to_dict()
    payload["status"] = embedder.status().to_dict()
    payload["persisted_to"] = str(out)
    return payload


@router.get("/api/ml/reports/embedding-status")
def ml_embedding_status():
    lake = _lake()
    embedder = ReportEmbedder(lake.models / "embedding_cache")
    return embedder.status().to_dict()


@router.post("/api/ml/cascade/simulate")
def ml_cascade_simulate(body: CascadeScenarioRequest):
    """Lightweight feature-level cascade simulation on ML zone rows.

    Distinct from PostGIS NetworkX cascade — marked as scenario only.
    """
    lake = _lake()
    try:
        scored = _ensure_scored(lake)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    hit = scored[scored["zone_id"].astype(str) == body.zone_id]
    if hit.empty:
        raise HTTPException(status_code=404, detail=f"Unknown zone_id={body.zone_id}")
    row = json.loads(hit.iloc[0].to_json())
    before = {
        "nearest_hospital_km": row.get("nearest_hospital_km"),
        "road_connectivity": row.get("road_connectivity"),
        "transit_accessibility": row.get("transit_accessibility"),
        "heuristic_vulnerability_score": row.get("heuristic_vulnerability_score"),
        "facility_count": row.get("facility_count"),
    }
    after = dict(before)
    assumptions: list[str] = []
    known: list[str] = [
        "Hospital access uses great-circle distance in the zone dataset.",
        "Road connectivity is an OSM-density proxy, not a traffic assignment model.",
    ]

    scenario = body.scenario.strip().lower()
    if scenario == "road_closure":
        # Assumed: connectivity drops; hospital distance increases 25% if present
        if after.get("road_connectivity") is not None:
            after["road_connectivity"] = max(0.0, float(after["road_connectivity"]) * 0.4)
        if after.get("nearest_hospital_km") is not None:
            after["nearest_hospital_km"] = float(after["nearest_hospital_km"]) * 1.25
        assumptions.append(
            "Assumed road closure reduces connectivity proxy by 60% and "
            "increases great-circle hospital distance by 25% (not network routing)."
        )
    elif scenario == "transit_suspension":
        if after.get("transit_accessibility") is not None:
            after["transit_accessibility"] = 0
        assumptions.append(
            "Assumed full suspension of mapped transit stops in the zone sample."
        )
    elif scenario == "power_facility_disruption":
        if after.get("facility_count") is not None:
            after["facility_count"] = max(0, int(after["facility_count"]) - 1)
        assumptions.append(
            "Assumed one dependent facility becomes unavailable (hypothesized dependency)."
        )
    else:
        raise HTTPException(
            status_code=422,
            detail="scenario must be road_closure | transit_suspension | power_facility_disruption",
        )

    # Recompute a local heuristic delta using the same engine on a one-row frame
    import pandas as pd
    from app.ml.vulnerability_models import transparent_vulnerability_score

    sim_row = dict(row)
    sim_row.update(after)
    sim_df = transparent_vulnerability_score(pd.DataFrame([sim_row]))
    after_score = sim_df.iloc[0].get("heuristic_vulnerability_score")
    after["heuristic_vulnerability_score"] = (
        float(after_score) if after_score == after_score else None
    )

    return {
        "kind": "simulation",
        "label": "HYPOTHETICAL SCENARIO — not an observed real-world event",
        "zone_id": body.zone_id,
        "scenario": scenario,
        "before": before,
        "after": after,
        "known_relationships": known,
        "assumptions": assumptions,
        "recommended_interventions": recommend_interventions(sim_row),
    }


@router.get("/api/ml/rankings")
def ml_rankings(city: Optional[str] = None, limit: int = Query(default=50, ge=1, le=500)):
    lake = _lake()
    try:
        scored = _ensure_scored(lake)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    df = scored
    if city:
        df = df[df["city"] == city.strip().lower()]
    df = df.sort_values(
        by=["heuristic_vulnerability_score", "anomaly_score"],
        ascending=[False, False],
        na_position="last",
    ).head(limit)
    items = []
    for _, row in df.iterrows():
        items.append(
            {
                "zone_id": row.get("zone_id"),
                "city": row.get("city"),
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "risk_score": row.get("heuristic_vulnerability_score"),
                "risk_category": row.get("heuristic_category"),
                "anomaly_score": row.get("anomaly_score"),
                "anomaly_flag": bool(row.get("anomaly_flag")),
                "source_coverage_score": row.get("source_coverage_score"),
                "data_quality_flag": row.get("data_quality_flag"),
            }
        )
    return {
        "items": items,
        "disclaimer": "Heuristic + anomaly rankings only.",
    }

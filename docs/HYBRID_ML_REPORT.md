# Hybrid ML Implementation Report — Critical 1%

**Date:** 2026-10-25  
**Workspace focus:** `model/` + `backend/app/ml/`

## 1. Files created or modified

### Created
- `backend/app/ml/` — `zone_dataset.py`, `vulnerability_models.py`, `embeddings.py`, `explain.py`, `clusters.py`, `interventions_rules.py`, `status.py`, `feature_catalog.py`
- `backend/app/api/ml_intelligence.py` — `/api/ml/*` routes
- `backend/app/scripts/run_ml_pipeline.py`
- `backend/tests/test_ml_intelligence.py`
- `model/README.md`, `model/pipeline/run_pipeline.py`
- `docs/HYBRID_ML_REPORT.md` (this file)

### Modified
- `backend/app/main.py` — register ML router
- `backend/requirements.txt` — catboost, xgboost, shap, sentence-transformers (optional)
- `frontend/src/lib/api.ts` — ML client methods
- `frontend/src/components/map/risk-map.tsx` — cluster layers from API
- `frontend/src/app/map/page.tsx` — load/toggle ML clusters

## 2. Datasets actually downloaded / used

| Source | Result |
|--------|--------|
| Open-Meteo Historical API | **Succeeded** for all 5 cities (city-centroid precip → estimated zone assign) |
| OSM Overpass (multiple mirrors) | **Failed** from this host (HTTP 406 / connect timeouts) — recorded in `city_stats` / raw summaries; features left **null** (not zero-filled) |
| Existing Nagpur EW parquet | Reused for CatBoost/XGBoost/sklearn benchmarks |
| Disaster report seed CSV | Available for embedding smoke / TF-IDF fallback |

## 3. Records and features

| Item | Value |
|------|--------|
| Zone analysis-grid records | **320** (5 cities × 8×8) |
| Columns / features | **31** |
| Parquet+CSV size | ~97 KB (under 50 MB target) |
| Geometry kind | `analysis_grid` (not official wards) |
| Population density | **null** (WorldPop deferred — never invented) |

## 4. Models trained or loaded

| Artifact | Kind | Claim |
|----------|------|--------|
| `zone_isolation_forest.joblib` | Isolation Forest | Unusual feature mixes — **not** crisis probability |
| Heuristic scores in `zones_scored.parquet` | Transparent weighted score | Configurable vulnerability — **not** supervised disaster prediction |
| `ew_bench_catboost_nagpur_h24.joblib` | CatBoost | Precip-proxy onset only |
| `ew_bench_xgboost_nagpur_h24.joblib` | XGBoost | Precip-proxy onset only |
| `ew_bench_sklearn_gb_nagpur_h24.joblib` | sklearn GB | Benchmark |
| Existing `ew_nagpur_h24.joblib`, `report_clf.joblib` | Prior stack | Unchanged |
| Report embeddings | **TF-IDF fallback** | `sentence_transformers` / e5 not installed on host |

## 5. Validation metrics (method stated)

**Early-warning supervised benchmarks** — chronological 75/25 split on monsoon-2023 Nagpur precip-proxy labels (`flood_onset_within_horizon`), threshold 0.5:

| Model | PR-AUC | Precision+ | Recall+ | Note |
|-------|--------|------------|---------|------|
| CatBoost | 0.137 | 0.0 | 0.0 | Proxy task; no useful +class at 0.5 |
| XGBoost | 0.084 | 0.0 | 0.0 | Same |
| sklearn GB | 0.074 | 0.0 | 0.0 | Same |

**Zone Isolation Forest:** fitted on 320 rows; features with all-null OSM columns dropped; anomaly ranking only.

**Unit/API tests:** `tests/test_ml_intelligence.py` + `tests/test_api.py` → **13 passed**.

## 6. Reproduce

```bash
cd backend
# Windows
.\.venv\Scripts\activate
pip install -r requirements.txt
# Optional: pip install sentence-transformers   # for multilingual-e5-small

$env:DATABASE_URL="postgresql+psycopg://critical1:critical1_dev@localhost:5433/critical1"
$env:DATA_DIR="./data"
python -m app.scripts.run_ml_pipeline

# API
uvicorn app.main:app --reload --port 8000
# GET  /api/ml/status
# GET  /api/ml/clusters?city=nagpur
# GET  /api/ml/zones/{zone_id}/explanation
# POST /api/ml/cascade/simulate
```

Or from workspace: `python model/pipeline/run_pipeline.py` (adds backend to `sys.path`).

## 7. Tests executed

| Command | Result |
|---------|--------|
| `pytest tests/test_ml_intelligence.py -q` | 4 passed |
| `pytest tests/test_ml_intelligence.py tests/test_api.py -q` | 13 passed |
| FastAPI TestClient smoke on `/api/ml/*` + `/api/health` | Succeeded in-session |

## 8. Runtime and blockers

| Item | Value |
|------|--------|
| Full pipeline (first run w/ Overpass attempts) | ~170 s |
| Rebuild skip-Overpass + rescore | ~41 s |
| **Blocker:** OSM Overpass unreachable (406/timeouts) | Road/hospital/transit/drainage null until network allows |
| **Blocker:** `sentence-transformers` not installed | TF-IDF fallback active |
| CDS / GFD / IMD / NWDP | Unchanged prior blockers (credentials) |

## 9. Next highest-priority improvement

Re-run zone build when Overpass is reachable (or cache a small Geofabrik extract per city bbox) so hospital distance, road density, and transit features populate; then retrain Isolation Forest on the fuller feature matrix. Optionally `pip install sentence-transformers` for `intfloat/multilingual-e5-small`.

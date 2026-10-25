# Critical 1% — Hybrid ML workspace

This folder documents and reproduces the **zone-level spatial intelligence**
pipeline that integrates with the FastAPI app under `../backend`.

## What lives where

| Path | Role |
|------|------|
| `../backend/app/ml/` | Library: dataset, scoring, Isolation Forest, embeddings, clusters, SHAP proxies |
| `../backend/app/api/ml_intelligence.py` | HTTP API (`/api/ml/*`) |
| `../backend/data/` | Data lake (`raw/`, `processed/`, `models/`) — configured via `DATA_DIR` |
| `pipeline/run_pipeline.py` | One-shot reproducible build + train + smoke checks |

## Reproduce (from `backend/`)

```bash
cd ../backend
.\.venv\Scripts\activate   # Windows
pip install -r requirements.txt

# Build 5-city analysis-grid dataset (Open-Meteo + OSM Overpass)
python -m app.scripts.run_ml_pipeline

# Or via API (server running):
# POST /api/ml/dataset/build
# POST /api/ml/train
# GET  /api/ml/status
# GET  /api/ml/clusters
```

## Integrity rules

- Analysis-grid geometries are **not** official wards.
- Rainfall is **city-centroid** Open-Meteo applied to zones (`estimated`).
- Population density stays **null** until a verified source is wired.
- Heuristic scores ≠ trained disaster probabilities.
- Isolation Forest ranks unusual feature mixes — not crisis forecasts.
- CatBoost/XGBoost train only on documented precip-proxy labels when available.
- Cascading `/api/ml/cascade/simulate` outputs are **simulations**.

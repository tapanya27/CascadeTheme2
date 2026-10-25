# India Geodata Integration Report — Critical 1%

**Generated:** 2026-10-25 (measured on local pipeline run)  
**Catalog:** https://yashveeeeeeer.github.io/india-geodata/  
**Code:** `backend/app/ingestion/india_geodata/`, `backend/scripts/run_india_geodata_pipeline.py`

## Legend

| Tag | Meaning |
|-----|---------|
| **MEASURED** | Observed in this run (files, counts, metrics) |
| **BLOCKED** | Portal / auth / size policy prevented ingest |
| **OUT OF SCOPE** | Explicitly excluded (full catalog, buildings, Kathmandu) |

---

## 1. Coverage by city

| City | India Geodata | Notes |
|------|---------------|-------|
| Nagpur | Yes | Inventory polygons, wards, NIC health, WorldPop samples |
| Mumbai | Yes | + UMD slum boundaries |
| Chennai | Yes | + TN slum boundaries; NE monsoon window in labels |
| Guwahati | Yes | Highest polygon count in study bboxes |
| Kathmandu | **OUT OF SCOPE** | Nepal — India Geodata / IFI / IMD / NIC / SOI do not cover it |

---

## 2. Downloads actually performed (**MEASURED** sizes on disk)

| Asset | Source | Bytes (approx) | Status |
|-------|--------|----------------|--------|
| `INDIA_FLOOD_INVENTORY_V3.geojson` | GitHub `environment/flood-inventory` | **28.6 MB** | OK |
| `India_Flood_Inventory_v3.csv` | Zenodo 10.5281/zenodo.11275211 | **1.72 MB** | OK (attribute table) |
| `District_FloodedArea.csv` | Zenodo IFI-Impacts | **0.03 MB** | OK (impacts — not Atlas) |
| Flood Atlas district risk/frac JSON | GitHub `environment/flood-atlas` | **0.09 + 0.05 MB** | OK (**model-derived**, separate) |
| `LivingAtlas_Wards.parquet` | GitHub `urban/boundaries` | **9.84 MB** | OK → city clips |
| Mumbai / TN slum parquets | GitHub `urban/boundaries` | **0.99 + 0.88 MB** | OK |
| `ind_pd_2020_1km.tif` | WorldPop | **17.24 MB** | OK |
| `INDIA_HEALTH_FACILITIES_NIC.geojson` | GitHub `healthcare/facilities` | **47.2 MB** | OK → city clips |
| IMD 0.25° gridded rainfall | IMD Pune portal | — | **BLOCKED** (not ingested) |
| ALOS AW3D30 DEM tiles | JAXA portal | — | **BLOCKED** (not ingested) |
| Full NIC/SOI national roads | India Geodata infrastructure | multi-GB | **SKIPPED** (size policy) |
| Urban buildings (~9 GB) | India Geodata | — | **SKIPPED** (explicit) |
| Full ~160 GB catalog | — | — | **SKIPPED** |

**Total downloaded this integration (raw):** ~**107 MB** (not GB).

Rainfall features for training used **Open-Meteo Archive** as a documented non-IMD fallback (`rain_source_note` in model table).

---

## 3. Flood labels (Inventory ≠ Atlas)

### 3.1 Spatial filter — Inventory GeoJSON ∩ city bbox (**MEASURED**)

| City | Polygons intersecting bbox | Usable dated events |
|------|---------------------------:|--------------------:|
| Nagpur | 3 | 3 |
| Mumbai | 11 | 11 |
| Chennai | 10 | 10 |
| Guwahati | 24 | 24 |
| **Total** | **48** | **48** |

National inventory features in file: **1006**.

### 3.2 Daily panel construction (**MEASURED**)

- Positives: event `StartDate` day (parsed).
- Negatives: other monsoon-season days **only in years with ≥1 usable city event**.
- Unlabelled: all other days — **not** treated as confirmed non-floods.
- Chennai seasons: Jun–Sep + Oct–Dec; others Jun–Sep.

| Metric | Value |
|--------|------:|
| Daily labelled rows | 1190 |
| Positives | 29 |
| Negatives | 1161 |
| Positive prevalence | **2.44%** |

### 3.3 Zenodo CSV district-token match (supplementary, looser)

District-name matching without polygon intersection retained **517** text-matched rows — useful for exploration but **not** used for the primary model after GeoJSON became available (over-counts multi-district events).

### 3.4 Flood Atlas

District risk / max flood-fraction JSON loaded and summarized separately.  
**`flood_atlas_used_as_labels: false`** everywhere in training code and reports.

---

## 4. Features joined for vulnerability / exposure (**MEASURED**)

Artifact: `backend/data/processed/india_geodata/zone_features_india_geodata.parquet` — **200 rows** (50 demo zones × 4 India cities).

| Feature | Source | Notes |
|---------|--------|-------|
| Ward counts in bbox | Living Atlas wards clip | Nagpur 128, Mumbai 258, Chennai 190, Guwahati 60 |
| Slum polygon counts | UMD Mumbai / TNGIS TN | Mumbai 2547, Chennai 1087; Nagpur/Guwahati 0 in downloaded sets |
| WorldPop density 2020 | 1 km GeoTIFF sample at zone centroids | **200/200 non-null** |
| Nearest NIC healthcare (km) | City-clipped NIC points | Nagpur 85, Mumbai **1**, Chennai 4, Guwahati 21 facilities in study bboxes |
| Inventory event counts | GeoJSON / Zenodo summaries | Separate from Atlas |

Terrain / river proximity / SOI–NIC roads: **not** computed — DEM and national road layers not downloaded (portal / size).

Zone polygons remain the existing demo/hardcoded study grid for aggregation scaffolding; inventory and WorldPop/health attributes are real.

---

## 5. Model training — inventory labels + Open-Meteo rain (**MEASURED**)

Chronological split (no random shuffle): train 714 / val 238 / test 238  
(train_pos 15 / val_pos 5 / test_pos 9). Thresholds tuned on **validation only**.

| Model | Role | PR-AUC (test) | @0.5 P+ | @0.5 R+ | Val-tuned thr | @thr P+ | @thr R+ | Alerts @thr |
|-------|------|---------------|---------|---------|---------------|---------|---------|-------------|
| Logistic (balanced) | Baseline | **0.049** | 0.047 | 1.00 | 0.60 | 0.043 | 0.89 | 185 |
| **CatBoost** | Primary | **0.046** | **0.0** | **0.0** | 0.40 | 0.0 | 0.0 | 22 |
| XGBoost | Benchmark only | **0.071** | 0.091 | 0.11 | 0.30 | 0.05 | 0.22 | 40 |

Artifacts:

- `backend/data/models/ew_inventory_catboost.cbm`
- `backend/data/models/ew_inventory_xgboost.joblib`
- `backend/data/models/ew_inventory_train_report.json`

**Interpretation:** With only **29** city-bbox inventory positives, supervised flood early-warning remains **experimental**. Zero positive precision/recall at 0.5 for CatBoost is a measured result — not improved by fabrication. Prefer transparent **vulnerability / exposure ranking** (`zone_features_india_geodata.parquet` + existing Module-2 / hybrid heuristic scores) for decision support. Keep cascade simulations separate.

Prior precipitation-proxy benchmarks (PR-AUC ~0.137 CatBoost) remain in place under `ew_bench_*` and must not be conflated with inventory-label metrics.

---

## 6. Reproduce (cached — no re-download if files exist)

```bash
cd backend
.\.venv\Scripts\activate
pip install -r requirements.txt
python scripts/run_india_geodata_pipeline.py
# or skip network:
python scripts/run_india_geodata_pipeline.py --skip-download
```

API status includes India Geodata block via `GET /api/ml/status` → `india_geodata`.

---

## 7. Limitations (honest)

1. IMD gridded rainfall and ALOS AW3D30 not ingested — rainfall is Open-Meteo fallback; no DEM slope/HAND yet.
2. National river / NIC–SOI road layers skipped (multi-GB); healthcare NIC coverage is uneven (Mumbai bbox sparse).
3. Inventory polygon years for study bboxes cluster in **2014–2016** — limited temporal diversity.
4. Demo zone geometries are not official wards (wards used as counts / optional overlays).
5. Kathmandu cannot be trained on India Geodata.
6. Models are **not** operational flood forecasts.

---

## 8. Distinct product lines (preserved)

| Product | Location / API |
|---------|----------------|
| Flood hazard (inventory experimental EW) | `ew_inventory_*` models + label summaries |
| Community vulnerability | Scoring engine + `zone_features_india_geodata.parquet` + hybrid heuristic / IF |
| Cascading-failure simulations | Existing cascade / resilience APIs (unchanged) |
| Flood Atlas context | `flood_atlas_summary.json` only — never labels |

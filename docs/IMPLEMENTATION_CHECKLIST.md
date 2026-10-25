# Implementation Checklist — Critical 1% (Crises Before Crises)

Last updated: autonomous master build. Status values: DONE | IN_PROGRESS | BLOCKED | DEFERRED.

## Phase 1 — Repository & environment
- [x] Inspect existing Modules 1–4 architecture
- [x] Confirm PostGIS on :5433, no SQLite
- [x] Create this checklist + data-source manifest
- [x] Extend config for cities, data lake paths, CDS placeholders
- [x] Embedded hardcoded demo dataset (`backend/app/data/hardcoded_dataset.py`) — 50 zones × 5 cities
- [x] India Geodata city-scoped ingest + inventory-label CatBoost (see `docs/INDIA_GEODATA_INTEGRATION_REPORT.md`)

## Phase 2 — Dataset discovery & ingestion
- [x] City registry (multi-city, not Nagpur-only)
- [x] Reusable ingestion provider interface
- [x] Open-Meteo historical precipitation provider (no API key)
- [x] CDS ERA5 provider scaffold + credential blocker docs
- [x] City-parameterized OSM Overpass importer (roads as LineString when geometry present)
- [x] Disaster-report corpus downloader (Disaster Response Messages)
- [x] Flood-event label provider (precipitation-proxy + external hook; GFD/EE blocked without auth)
- [ ] WorldPop raster ingest (DEFERRED — large downloads; zone property import supported)
- [ ] IMD / NWDP live station APIs (BLOCKED — site terms / auth; hooks documented)

## Phase 3 — Temporal flood early-warning
- [x] Feature builder (1/3/6/24/72h rainfall aggregates)
- [x] Leakage-safe chronological split
- [x] Baseline logistic + sklearn GradientBoosting
- [x] Metrics: precision, recall, PR-AUC, false-alarm / miss rates
- [x] Model artifact + metadata persistence
- [x] Honest unavailable-model state when insufficient labels

## Phase 4 — Hidden community vulnerability
- [x] Hazard-only baseline score/rank
- [x] Multi-factor score/rank (existing engine)
- [x] Rank uplift = hazard_only_rank − multifactor_rank
- [x] API + dashboard fields for dual view
- [x] Keep forecast / vulnerability / confidence conceptually separate

## Phase 5 — Disaster-report intelligence
- [x] Report taxonomy + TF-IDF multilabel/binary classifiers
- [x] Duplicate / near-duplicate hashing
- [x] Location only from explicit metadata or high-confidence tokens
- [x] Privacy-conscious community report intake (PII redaction)
- [x] Human-review queue flag for low-confidence
- [x] Time-aware: reports usable for EW only if timestamp ≤ forecast time

## Phase 6 — Cascading-failure simulator
- [x] Link infra nodes to zones (spatial + assumed edges)
- [x] Scenarios: road closure, hospital outage, power, multi-fail, data-source loss
- [x] Recalculate accessibility features + rankings
- [x] Evidence vs assumption labelling in results

## Phase 7 — Resilience under data loss
- [x] 20% / 40% / 60% source-drop simulations
- [x] Stale / conflicting / noisy / duplicate report tests
- [x] Seeded, reproducible scenario logs
- [x] Explicit: no federated learning / no DP claims

## Phase 8 — Intervention planner
- [x] Evidence-linked temporary healthcare / route / accessibility actions (extend existing)
- [x] Wire dual-rank deltas into scenario payload when assessments present

## Frontend
- [x] City selector in shell
- [x] Dual ranking on overview / zones
- [x] Early warning, reports, cascade, resilience surfaces
- [x] OSM import by selected city

## ML validation (2026-10-25)
- [x] Leakage-aware EW evaluation harness + monsoon 2023 measured metrics
- [x] Dual-rank / NLP / cascade-resilience audits with JSON evidence
- [x] `docs/ML_VALIDATION_REPORT.md` (measured vs estimated vs simulated)
- [x] PII long-digit fix; seed NLP corpus expansion; 74 backend tests passing

## Phase 9 — Hybrid ML (CatBoost / IF / e5 / clusters) — 2026-10-25
- [x] Multi-city analysis-grid zone dataset pipeline (`backend/app/ml/zone_dataset.py`)
- [x] Transparent heuristic vulnerability scoring (not labelled as supervised disaster model)
- [x] Isolation Forest anomaly ranking on zone features
- [x] CatBoost + XGBoost + sklearn GB precip-proxy benchmarks (honest low +class metrics)
- [x] Report embed/cluster with multilingual-e5 preferred, TF-IDF fallback
- [x] `/api/ml/*` status, zones, explanation, clusters, cascade sim, interventions
- [x] Map page consumes `GET /api/ml/clusters` (real API GeoJSON)
- [x] Docs: `docs/HYBRID_ML_REPORT.md`, `model/README.md`
- [ ] OSM Overpass live enrich (BLOCKED on this host — 406/timeouts; nulls preserved)
- [ ] sentence-transformers / e5 download (DEFERRED — TF-IDF fallback verified)

## Blockers requiring human action
- CDS Copernicus account + accepted ERA5 terms + `CDSAPI_URL` / `CDSAPI_KEY`
- Google Earth Engine auth for Global Flood Database rasters
- IMD / NWDP access agreements for operational Indian hydrology feeds
- Stable mirror for full Disaster Response Messages CSV (seed corpus in use)
- OSM Overpass reachability (or local Geofabrik extract) for zone road/hospital/transit features
- Optional: `pip install sentence-transformers` for `intfloat/multilingual-e5-small`

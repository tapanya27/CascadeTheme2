# The Critical 1%: Hidden Community Vulnerability

City-agnostic spatial intelligence for flood early-warning proxies, hidden community vulnerability (hazard-only vs multi-factor ranks), disaster-report NLP, cascading-failure and resilience simulations.

**Default city:** Nagpur (switchable via sidebar / `DEFAULT_CITY_ID` / `/api/cities`). Also includes Mumbai, Chennai, Guwahati, Kathmandu.

| Capability | Status |
|------------|--------|
| Modules 1–4 foundation | Intact — PostGIS, scoring, map, interventions |
| Multi-city + OSM by bbox | Implemented |
| Open-Meteo weather ingest | Implemented (no API key) |
| CDS ERA5 | Scaffold — needs `CDSAPI_KEY` + dataset terms |
| Early-warning model | Implemented (proxy labels until official events) |
| Dual rank + uplift | Implemented |
| Disaster-report NLP | Implemented (seed/corpus; not a live feed) |
| Cascade + 20/40/60% resilience | Implemented |
| GFD / EE / IMD / NWDP | Blocked — credentials or portal access |

See `docs/IMPLEMENTATION_CHECKLIST.md` and `docs/DATA_SOURCE_MANIFEST.md`.

**Forecast likelihood, vulnerability ranking, and data-quality confidence are separate concepts.** Scores and simulations are not validated operational forecasts or causal proofs.

---

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js App Router, TypeScript, Tailwind CSS, shadcn-style UI, Lucide, Leaflet/React Leaflet, Recharts, React Flow |
| Backend | Python 3.11+, FastAPI, Pydantic, Pandas, NumPy, GeoPandas, Shapely, NetworkX, scikit-learn |
| Database | **PostgreSQL + PostGIS only** (SQLAlchemy 2.x, Alembic, Psycopg 3) |

**SQLite is not supported.** The application will not fall back to SQLite, in-memory storage, or mock repositories.

---

## Repository layout

```
├── docker-compose.yml          # PostGIS 16
├── .env.example
├── README.md
├── backend/
│   ├── app/                    # FastAPI application
│   │   ├── api/                # Routes
│   │   ├── models/             # SQLAlchemy ORM
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── repositories/
│   │   ├── services/           # Import, OSM, synthetic, assessments, graph
│   │   ├── scoring/            # Configurable vulnerability engine
│   │   ├── geospatial/
│   │   └── scripts/
│   ├── alembic/                # Migrations
│   ├── data/samples/           # Example CSV / GeoJSON
│   ├── tests/
│   └── requirements.txt
└── frontend/                   # Next.js dashboard shell
```

---

## Quick start

### 1. Environment

```bash
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```

Key variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | `postgresql+psycopg://critical1:critical1_dev@localhost:5433/critical1` |
| `CORS_ORIGINS` | Frontend origin(s), e.g. `http://localhost:3000` |
| `SPATIAL_SRID` | Default `4326` (WGS84) |
| `OSM_ENABLED` | Toggle Overpass importer |
| `SCORING_WEIGHTS_JSON` | Optional JSON weight overrides for Module 2 |
| `MAX_UPLOAD_BYTES` | Upload size cap (default 5_000_000) |
| `RATE_LIMIT_EXPENSIVE_PER_WINDOW` | Cap for import/assess/compare calls |
| `APP_ENVIRONMENT` | `development` / `production` label for logs |
| `NEXT_PUBLIC_API_BASE_URL` | Backend URL for the frontend client |
| `DEFAULT_CITY_ID` | Active study city id (e.g. `nagpur`, `mumbai`) |
| `DATA_DIR` | Data lake root for raw/processed/models (default `./data` from backend cwd) |
| `CDSAPI_KEY` | Optional Copernicus CDS key (`uid:api-key`) for ERA5 downloads |

### 2. Start PostgreSQL / PostGIS

```bash
docker compose up -d
```

Wait until healthy (`docker compose ps`). PostGIS is enabled via `backend/scripts/init_postgis.sql` and again in Alembic migrations.

### 3. Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

# Apply migrations (creates tables + spatial indexes)
alembic upgrade head

# Load embedded hardcoded demo data (250 zones across 5 cities — no downloads)
python -m app.scripts.seed_synthetic
# Or one city: python -m app.scripts.seed_synthetic --city mumbai

# Run API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs  
Health: http://localhost:8000/api/health

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

---

## API endpoints

### Module 1 — data foundation

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | App + PostgreSQL/PostGIS connectivity |
| `GET` | `/api/metadata` | Project / module metadata |
| `GET` | `/api/zones` | Paginated zones (+ optional latest score fields) |
| `GET` | `/api/zones/{zone_id}` | Zone detail |
| `GET` | `/api/data/sources` | Data source provenance list |
| `POST` | `/api/data/validate` | Preview/validate CSV or GeoJSON (multipart) |
| `POST` | `/api/data/import` | Validate then optionally commit import |
| `GET` | `/api/data/export` | Export zones, infrastructure, hazards, sources |
| `POST` | `/api/data/osm/import` | OSM Overpass import for Nagpur (configurable) |
| `POST` | `/api/data/synthetic/seed` | Seed synthetic demonstration dataset |

### Module 2 — scoring & intelligence

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/zones/{zone_id}/explanation` | Latest assessment narrative + components |
| `POST` | `/api/assessments/run` | Compute & persist assessments (optional weight overrides) |
| `GET` | `/api/assessments/latest` | Latest assessment run per zone |
| `GET` | `/api/dependency-graph` | NetworkX-backed dependency graph JSON |

### Module 3 — dashboard payloads

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/dashboard/overview` | Category counts, high-priority zones, freshness |
| `GET` | `/api/map/layers` | PostGIS GeoJSON zones + hazards + infrastructure |
| `GET` | `/api/zones/{zone_id}/context` | Hazards/infrastructure intersecting a zone |

### Module 4 — interventions & robustness

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/interventions/compare` | Evaluate & persist a scenario (simulation) |
| `GET` | `/api/interventions` | Scenario history + intervention catalog |
| `GET` | `/api/interventions/{scenario_id}` | Scenario detail |
| `POST` | `/api/assessments/sensitivity` | Weight perturbation ranking sensitivity |

Intervention types (only when inputs allow evaluation): temporary resource placement (`lon`/`lat`), accessibility improvement (user-supplied assumed km **or** placement), alternative route (user-supplied disruption assumption), compare placements. **Missing required inputs → HTTP 422** (values are never invented).

---

## Frontend navigation (Module 3)

| Route | Purpose |
|-------|---------|
| `/` | Overview stats, category chart, high-priority list, map preview |
| `/map` | Interactive Leaflet map with filters, layers, legend, zone selection |
| `/zones` | Zone list with scores; run assessments |
| `/zones/[zoneId]` | Full score breakdown, healthcare notes, local hazards/infra |
| `/dependencies` | React Flow graph with evidence panel |
| `/data` | Validate → confirm import, sources history, export |
| `/interventions` | Scenario compare, history, weight sensitivity |

Map tiles use OpenStreetMap with attribution. Synthetic geometries and sources are badged. Empty/loading/error/retry states are wired to live API calls — failed responses are not replaced with fabricated production data.

---

## Module 2 — scoring methodology

Scoring version: **`v1.0-nagpur-flood-health`**.

Components (default weights; change via `SCORING_WEIGHTS_JSON` or `weight_overrides` on `/api/assessments/run` without rewriting the engine):

| Component | Direction | Default weight | Normalization | Limitations |
|-----------|-----------|----------------|---------------|-------------|
| `flood_hazard_exposure` | higher → worse | 0.30 | severity-weighted intersecting hazards → 0–100 | Sparse markers ≠ official flood stats |
| `population_exposure` | higher → worse | 0.15 | population property if present | **Never invented**; unavailable if missing |
| `road_disruption_risk` | higher → worse | 0.20 | flood–road co-location proxy | Not a traffic model |
| `healthcare_travel_burden` | higher → worse | 0.25 | km to nearest facility (great-circle) | Not network travel time / ETA |
| `infrastructure_availability` | higher → better (inverted) | 0.10 | facility count in zone | Presence ≠ capacity |

**Missing data:** unavailable components are **excluded**; remaining weights are **renormalized**. Values are never silently zero-filled.

**Categories:** low `[0,25)`, moderate `[25,50)`, high `[50,75)`, critical `[75,100]`.

**Persisted in PostgreSQL:** `vulnerability_assessments` (inputs, components, weights, reasons, quality, confidence, narrative) and `dependency_edges` (observed / assumed / hypothesized relationships).

**Dependency graph:** candidate pathways (e.g. rainfall → flood → road disruption → travel burden → accessibility). Edges store evidence kind and provenance; hypothesized edges are **not** proven causation.

### Import form fields

- `file` — `.csv`, `.geojson`, or `.json`
- `record_type` — `zones` | `infrastructure` | `hazards`
- `commit` — `true` / `false` (preview when false)
- `source_name` — optional provenance name
- `source_epsg` — optional source CRS for GeoJSON
- `is_synthetic` — mark upload as synthetic

**CSV columns**

- Zones: `code`, `name`, `wkt` (+ optional `description`)
- Infrastructure: `name`, `infrastructure_type`, `lon`, `lat` (+ optional `external_id`)
- Hazards: `hazard_type`, `lon`, `lat` (+ optional `severity`, `observed_on`, `description`)

Invalid rows are **never** silently discarded — validation returns per-row issues and import aborts on failure (transaction rollback).

---

## Synthetic data policy

If authentic flood/infrastructure feeds are unavailable, seed synthetic data via:

```bash
python -m app.scripts.seed_synthetic
# or POST /api/data/synthetic/seed
```

Synthetic records:

- Are stored under a data source with `is_synthetic=true`
- Include provenance / disclaimer metadata
- Are labelled in the UI with a **Synthetic** badge
- Must **not** be presented as verified real-world measurements

---

## Testing

```bash
cd backend
pytest -q
```

Coverage includes:

- SQLite rejection / PostgreSQL URL normalization
- Geometry & coordinate validation
- CSV / GeoJSON validation (invalid coords, malformed geometry)
- Health / metadata / API error handling
- Live DB connectivity, models, synthetic provenance (when PostGIS is up)
- Score normalization, weighting, thresholds, repeatability, missing-data handling
- Assessment persistence, zone explanations, dependency graph metadata

Frontend checks:

```bash
cd frontend
npm run lint
npm run typecheck
npm test
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `DATABASE_URL` validation error mentioning SQLite | Use a `postgresql+psycopg://…` URL only |
| Health `database: unavailable` | `docker compose up -d` and confirm port **5433** (or your `POSTGRES_PORT`) |
| Password auth failed on 5432 | Another local Postgres may own 5432 — this project maps PostGIS to host port **5433** by default |
| Health connected but `postgis: false` | Ensure image is `postgis/postgis` and re-run `alembic upgrade head` |
| Alembic cannot connect | Export/load `.env` from repo root; run Alembic from `backend/` |
| CORS errors in browser | Set `CORS_ORIGINS=http://localhost:3000` |
| OSM import timeout / 429 | Set `OSM_ENABLED=false` or retry later; use synthetic seed for local demo |
| Frontend “API base URL not set” | Copy `frontend/.env.local.example` → `.env.local` |

---

## Module 4 — interventions, privacy, deployment

- Scenarios persist in `intervention_scenarios` (Alembic `20260325_0003`).
- Outputs are labelled **simulations**, not guaranteed outcomes.
- Weight sensitivity exposes ranking stability under heuristic weight changes — **not** ML validation.
- Privacy notes: [docs/PRIVACY.md](docs/PRIVACY.md).
- Optional API container: `docker compose --profile full up -d --build` (runs migrations on start). Persistent PostGIS volume: `critical1_pgdata`.
- Fresh DB path: `docker compose up -d` → `alembic upgrade head` → seed/import → assess → intervene.

## Scope

**Modules 1–4 included** in this repository. Remaining limitations: geometric (not network) travel distances; OSM coverage gaps; synthetic demo data for local testing; intervention effects are heuristic feature adjustments under explicit assumptions only.

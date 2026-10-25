# Multi-city data isolation fix report

**Date:** 2026-10-25  
**Issue:** Selecting Kathmandu (or any non-Nagpur city) still showed Nagpur map, zones (`NAG-SYN-*`), intervention coordinates (~79.09, 21.15), and assessments.

## Root causes

1. **UI city selector was presentation-only.** Sidebar `cityId` was stored in React context / localStorage but most pages called APIs without `city_id`.
2. **Backend geospatial tables lacked `city_id`.** Zones, infrastructure, hazards, and data sources were globally unique / unscoped, so every query returned the Nagpur synthetic seed.
3. **Map hard-coded Nagpur.** `risk-map.tsx` used a fixed `NAGPUR_CENTER`; map subtitle said “Nagpur study area” regardless of selection.
4. **Interventions hard-coded Nagpur lon/lat** (`79.09` / `21.15`) instead of deriving coordinates from the selected zone’s geometry.
5. **OSM / synthetic import were not city-scoped** (or defaulted to Nagpur), so other cities could inherit or appear to share Nagpur records.
6. **Assessment, intervention history, cascade, and resilience** queried all zones without filtering by city, so Nagpur scenarios leaked into other city views.

## What changed

### Database (safe migration)

- Alembic `20261025_0005_city_isolation.py`:
  - Adds non-null `city_id` to `data_sources`, `zones`, `infrastructure`, `hazard_observations`
  - Backfills existing rows to `city_id='nagpur'` (no deletes / no table drops)
  - Replaces global uniqueness with `(city_id, code)` / `(city_id, name)`

### Backend

- `app/cities/deps.py`: required `city_id` query dependency for city-scoped routes
- All list/get/run endpoints for zones, dashboard, map layers, assessments, interventions, data sources/export/import/OSM/synthetic, cascade, resilience, dependency graph accept and enforce `city_id`
- Feature extraction, scoring, intervention compare/list/get join/filter via `Zone.city_id`
- Synthetic seed **only** creates Nagpur demo data; other cities get an explicit refusal (never copy Nagpur rows)
- OSM import requires `city_id` and persists rows under that city’s bbox
- Imports stamp `city_id` on sources and records; hazards labelled as imported/unverified, not “confirmed flood”

### Frontend

- `api.ts` appends `city_id` on every city-scoped request
- Overview, Map, Zones, Interventions, Data, Dependencies, Cascade & resilience use `useCity()` and reload on city change
- Map center/fit uses selected city centroid + empty state with import CTA
- Interventions derive lon/lat from the selected zone’s GeoJSON centroid
- Empty states for cities without data; no fabricated fill from Nagpur

## City-by-city data availability (after fix)

| City ID     | Zones / infra / hazards (default DB) | Early-warning model | Notes |
|-------------|--------------------------------------|---------------------|-------|
| `nagpur`    | Synthetic demo present after seed (`NAG-SYN-01`…`04`) | Separate artifact path per city; train after weather ingest | Original demo study area preserved |
| `kathmandu` | Empty until import                         | Unavailable until city-specific weather + train | Empty dashboard/map/zones/interventions |
| `mumbai`    | Empty until import                         | Same                | Empty until import |
| `chennai`   | Empty until import                         | Same                | Empty until import |
| `guwahati`  | Empty until import                         | Same                | Empty until import |

Import options per city: OSM Overpass for that city’s bbox, or CSV/GeoJSON upload with `city_id`.

## Tests

### Backend (`pytest`)

- **83 passed** (full `backend/tests`)
- New `tests/test_city_isolation.py` proves:
  - Kathmandu zones/map/assessments/interventions do not return Nagpur data
  - Cross-city zone GET / intervention compare returns 404/422
  - Switching all registry cities keeps Nagpur populated and others empty
  - Synthetic seed refuses non-Nagpur cities
  - `city_id` is required on `/api/zones`

### Frontend

- **7 passed** (`vitest`), including city_id query assertion on map/zones
- `tsc --noEmit` clean

## Changed files (primary)

- `backend/alembic/versions/20261025_0005_city_isolation.py`
- `backend/app/models/{zone,data_source,infrastructure,hazard}.py`
- `backend/app/cities/deps.py`
- `backend/app/api/{dashboard,zones,assessments,interventions,data,cascade,resilience,dependencies}.py`
- `backend/app/services/{dashboard_service,intervention_service,assessment_service,import_service,osm_importer,synthetic_data,cascade_simulator,resilience_service,dependency_graph,sensitivity_service}.py`
- `backend/app/repositories/{zones,assessments,data_sources}.py`
- `backend/app/scoring/features.py`
- `backend/tests/test_city_isolation.py` (+ updated API tests)
- `frontend/src/lib/{api.ts,types.ts,zone-centroid.ts,city-context.tsx}`
- `frontend/src/components/map/risk-map.tsx`
- `frontend/src/app/{page,map,zones,interventions,data,dependencies,intelligence}/**`

## Verification commands

```bash
cd backend && .venv/Scripts/python.exe -m alembic upgrade head
cd backend && .venv/Scripts/python.exe -m pytest tests -q
cd frontend && npm test && npx tsc --noEmit
```

Restart API + Next.js after migration so the running UI picks up city-scoped responses.

-- Enable PostGIS on first container init (also re-checked by Alembic migrations).
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

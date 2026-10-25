# Privacy and responsible use

This platform is designed around **aggregated geographical indicators** for disaster-intelligence analysis in Nagpur. It is **not** a clinical system and must not ingest identifiable personal health records (names, patient IDs, free-text medical notes, household addresses of individuals, etc.).

## What we store

- Zone polygons and codes
- Infrastructure and hazard geometries with provenance
- Vulnerability assessments and intervention **simulations**
- Data-source metadata

## What we do not claim

Removing names does **not** make a dataset completely privacy-safe. Small-area geographic aggregation can still enable **re-identification** when combined with other public data, especially for sparsely populated zones.

## Controls implemented

- Upload type restrictions (`.csv`, `.geojson`, `.json` only)
- Configurable upload size limit (`MAX_UPLOAD_BYTES`)
- Rate limits on expensive imports / assessments / scenario comparisons
- CORS origins from environment (`CORS_ORIGINS`)
- Secrets via environment variables (never commit `.env`)
- Public error messages that avoid credentials and stack traces
- Logging that avoids printing connection strings with passwords

## Operator guidance

- Prefer official aggregated statistics over household-level imports
- Mark synthetic demo data clearly (`is_synthetic`)
- Treat intervention outputs as simulations, not operational guarantees

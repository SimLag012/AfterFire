# Running and maintaining AfterFire

Use the [README](../README.md#get-started) for installation and the [scientific methodology](SCIENTIFIC_METHODOLOGY.md) for interpretation. Run commands below from the repository root unless a different directory is specified.

## Services and acquisition

FastAPI and `python -m app.jobs.analysis_worker` share the database and scientific cache. Compose starts PostgreSQL/PostGIS, the API, worker and frontend. The local launcher starts API, worker and Vite with `backend/afterfire.db` and `.local-runtime/analysis-cache`; this SQLite database is separate from the Docker volume.

Normal acquisition follows **saved publication → verified native cache → configured compatible Collection 6.1 API → explicit unavailable result**. Cached HDFs remain readable. Missing data does not automatically trigger full-tile HDF downloads or a new AppEEARS submission. Those require explicit opt-in in [.env.example](../.env.example).

Jobs retain progress, source identity, parameters, algorithm version and publication fingerprints. An unchanged request can reuse its result; explicit retries preserve the last valid publication if the new attempt fails. API and worker must use the same credentials, database and cache. Keep the worker running for new analyses and historical acquisition.

## Earth Engine

Register a project through the [Earth Engine access procedure](https://developers.google.com/earth-engine/guides/access), enable the API and configure an identity with the required access. Authenticate locally with Application Default Credentials:

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_REGISTERED_PROJECT_ID
```

Keep the ADC file outside the repository. For the file-based Compose overlay, set the following in the private root `.env`:

```dotenv
AFTERFIRE_API_FIRST=true
AFTERFIRE_SATELLITE_PROVIDER=earth_engine
AFTERFIRE_EARTH_ENGINE_ENABLED=true
AFTERFIRE_EE_PROJECT_ID=YOUR_REGISTERED_PROJECT_ID
AFTERFIRE_GOOGLE_CREDENTIALS_FILE=/absolute/private/path/application_default_credentials.json
AFTERFIRE_APPEEARS_SUBMISSION_ENABLED=false
AFTERFIRE_FULL_HDF_AUTO_DOWNLOAD=false
```

The overlay mounts the existing file read-only into API and worker. Use both Compose files for subsequent recreations:

```bash
docker compose -f compose.yaml -f compose.earth-engine.yaml up -d --build backend analysis-worker
docker compose -f compose.yaml -f compose.earth-engine.yaml exec -T backend python -m app.providers.earth_engine_check --live
docker compose -f compose.yaml -f compose.earth-engine.yaml exec -T analysis-worker python -m app.providers.earth_engine_check --live
```

The bounded live probe checks real MOD13Q1/MCD64A1 reads without publishing an analysis. Configuration alone is not proof of access; a passed probe is not proof of complete multiyear coverage. Authentication, quota and provider failures remain explicit. SDK telemetry counts decoded array bytes, not exact HTTP wire traffic. Managed runtime identities can provide ADC without the file overlay.

## Import FIRMS history

The importer retains original attributes, dataset/version, satellite, acquisition time, confidence and provenance. Repeated ingestion uses checkpoints; imports do not establish complete observational coverage.

For local SQLite, use the backend environment and explicitly select its database:

```bash
cd backend
DATABASE_URL=sqlite+aiosqlite:///./afterfire.db .venv/bin/python \
  ../scripts/import_italy_fire_history.py --api-history --chunk-size 10000
DATABASE_URL=sqlite+aiosqlite:///./afterfire.db .venv/bin/python \
  ../scripts/index_fire_events.py
```

The Italy importer downloads resumable annual country files; `--api-history` also fills available gaps through authenticated FIRMS requests and requires `FIRMS_MAP_KEY`. Do not put the key in a command line. Use `import_firms_archive.py --help` for individual CSV imports or bounded recent products.

For the configured Docker database, mount the scripts and retained download directory into a one-off backend process:

```bash
docker compose run --rm --no-deps -e PYTHONPATH=/app \
  -v "$PWD/scripts:/scripts:ro" \
  -v "$PWD/backend/data/firms-italy:/app/data/firms-italy" \
  backend python /scripts/import_italy_fire_history.py --api-history --chunk-size 10000
docker compose run --rm --no-deps -e PYTHONPATH=/app \
  -v "$PWD/scripts:/scripts:ro" backend python /scripts/index_fire_events.py
```

Candidate indexing is required after archive imports. It groups observations algorithmically; it does not create official fire perimeters. A missing or empty archive cannot demonstrate absence of fire.

## Storage and recovery

The Compose database and provider caches use persistent volumes. The scientific cache contains source/subset files, native processed checkpoints, result rasters, manifests and locks. Checksums, source identity and native-grid validation govern reuse. Incomplete files never count as valid sources.

Defaults include a 10 GiB scientific cache, 5 GiB of new scientific transfers per job, 1 GiB temporary/block limits, a 2 GiB result limit and 1 GiB free-space reserve; [.env.example](../.env.example) and backend Settings define the actual configuration. Catalog metadata has separate TTL-based caching. Cache hits do not consume the new-network-byte budget.

Cleanup uses exclusive locks and protects active work, published assets and provenance. Original HDF eviction requires both `AFTERFIRE_ANALYSIS_KEEP_SOURCE_GRANULES=false` and `AFTERFIRE_ANALYSIS_CACHE_POLICY=lru_sources`; current reclaimable subset/checkpoint policies remain separate. Cache inventory is available through `GET /api/v1/admin/satellite-cache` only with the configured administrator bearer token. There is no public scientific-result deletion endpoint. Imported FIRMS records are outside satellite-cache eviction.

Restart API/worker with the same database and cache to resume persistent jobs; expired leases can be reclaimed. Inspect status and provider warnings before retrying. Preserve the volumes when recreating services.

## API and tests

The running FastAPI [OpenAPI documentation](http://localhost:8000/docs) is the complete endpoint reference. Common routes under `/api/v1` include:

| Workflow | Routes |
| --- | --- |
| Explorer | `/explorer/hotspots`, `/explorer/clusters`, `/explorer/events`, `/events/{id}` |
| Event analysis | `/events/{id}/analysis`, `/analysis/status`, `/analysis/result`, `/analysis/stream` |
| Planning | `POST /events/{id}/analysis/preflight` returns 202 and a planning ID; GET/SSE retrieves the persisted plan |
| Recovery | `/events/{id}/recovery-assessment`, `/recovery-assessment/result`, `/recovery-assessment/map`, `/recovery-assessment/cells/{cell}` |
| Reburn | `/events/{id}/reburn-analysis`, `/reburn-map`, `/reburn-cells/{cell}` |
| Historical activity | `/fire-activity/studies`, `/studies/{id}`, `/studies/{id}/status`, `/studies/{id}/months/{month}` |

Suffixes in each event row share the `/events/{id}` prefix. Reading saved publications or changing map visibility does not request a new scientific acquisition. Planning is optional and does not acquire scientific files or submit NASA tasks.

```bash
# From afterfire/, with backend dependencies installed.
backend/.venv/bin/python -m pytest backend/app/tests -q
npm --prefix frontend run build
```

Test fixtures use temporary SQLite/cache directories. Optional PostgreSQL tests require a dedicated `AF_TEST_DATABASE_URL` whose database name starts with `afterfire_test_`. Exporter regressions live in `backend/app/tests/test_vercel_export.py`.

## Essential scripts

Only these nine executable tools remain in `scripts/`:

| Tool | Required use |
| --- | --- |
| `local.py` | Start API, worker and Vite locally |
| `check_secrets.py` | Credential checks used by CI, the pre-commit hook and tests |
| `import_firms_archive.py` | FIRMS CSV/recent ingestion and shared import implementation |
| `import_italy_fire_history.py` | Resumable Italy archive ingestion |
| `index_fire_events.py` | Build candidate membership after imports |
| `prepare_vercel_clone.py` | Prepare the static clone from the original frontend |
| `export_vercel_demo.py` | Export allowlisted existing scientific publications |
| `export_vercel_demo_docker.py` | Run that export in the existing local scientific container |
| `check_vercel_clone.py` | Validate snapshot integrity and source/style parity before publication |

`vercel_demo_selection.json` is the export allowlist, not an executable. See [Vercel demo](VERCEL_CLONE.md) for the publishing workflow. Development starts through `local.py`; builds, preview and tests use their standard npm/pytest commands.

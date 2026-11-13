# AfterFire backend: Italy archive and explorer

For the configured Docker/PostgreSQL application, run from the repository root:

```sh
docker compose build backend frontend
docker compose up -d --no-deps backend frontend
docker compose run --rm --no-deps -e PYTHONPATH=/app \
  -v "$PWD/scripts:/scripts:ro" \
  -v "$PWD/backend/data/firms-italy:/app/data/firms-italy" \
  backend python /scripts/import_italy_fire_history.py --api-history --chunk-size 10000
```

This imports into the existing configured PostgreSQL database; it does not replace
or reset its volume. The mounted download directory retains resumable files and
receipts between runs. Hotspot IDs and checkpoints make re-runs idempotent.

For local SQLite development, run commands from `backend` using its environment
(`.venv/bin/python` locally).
The backend reads `.env` in its working directory. Set `DATABASE_URL` explicitly
when selecting SQLite instead of the configured PostgreSQL service.

## Historical ingestion

```sh
DATABASE_URL=sqlite+aiosqlite:///./afterfire.db .venv/bin/python \
  ../scripts/import_italy_fire_history.py --api-history --chunk-size 10000
```

The historical importer reads NASA's official
[annual country index](https://firms.modaps.eosdis.nasa.gov/data/country/yearly_summary_files.txt),
selects only Italy CSVs, checks download size and update metadata, and imports
all available years. `--api-history` additionally checks live FIRMS availability
and fills products/years absent from the annual index, using standard processing
first, followed by nonoverlapping NRT dates, in windows of at most five days.
This option requires the existing `FIRMS_MAP_KEY`; never place the key in a command
line or a committed file. A failed request stops with a source/date error; rerun
to resume downloaded files and committed checkpoints.

Annual MODIS CSVs retain their exact FIRMS `version` under
`FIRMS_MODIS_ANNUAL`. The version field is not silently interpreted as a new
collection name. Other configured products are `FIRMS_MODIS_C61`,
`FIRMS_VIIRS_SNPP_375M`, `FIRMS_VIIRS_NOAA20_375M`, and
`FIRMS_VIIRS_NOAA21_375M`. Each observation retains raw attributes, satellite,
original version, date/time and source dataset. Annual files and NRT windows
can contain processing revisions; deterministic IDs deduplicate matching product,
satellite, acquisition time and coordinates, without merging distinct sensors.

Downloads and receipts are in `data/firms-italy/` (ignored by Git). The
`import-summary.json` and `api-history/availability.json` record what was fetched;
SQL checkpoints record processed, imported, duplicate, invalid and outside counts.
A completed file is not a guarantee that NASA's entire geographic or temporal
archive is complete. No downloads run during map/circle queries.

Local archive CSVs can also be imported independently:

```sh
.venv/bin/python ../scripts/import_firms_archive.py \
  --csv /path/to/export.csv --product VIIRS_NOAA21_SP
```

This validates required columns, finite coordinates and measurements, dates,
HHMM, product/instrument/satellite identity and the versioned Italy polygon.
Each chunk and its file SHA-256/product checkpoint commit together. Rerunning an
interrupted file resumes after the last committed row; changed files are counted
independently, while detection IDs prevent duplicate inserts.

Boundary: the bundled `data/natural_earth_5_1_2_italy.geojson` is the Italy subset
of [Natural Earth 1:10m Admin-0 countries, v5.1.2](https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-0-countries/),
public domain. It includes islands and excludes national enclaves. This is a
cartographic boundary, with coastline/scale uncertainty, not a cadastral survey.

## Recent updates and candidate indexing

```sh
.venv/bin/python ../scripts/import_firms_archive.py --recent --product MODIS_C61 --days 5
.venv/bin/python ../scripts/import_firms_archive.py --recent --product VIIRS_NOAA20_SP --days 5
.venv/bin/python ../scripts/import_firms_archive.py --recent --product VIIRS_NOAA21_SP --days 5
.venv/bin/python ../scripts/index_fire_events.py
```

Recent updates use MODIS_NRT and the matching satellite's VIIRS_NRT product;
allowed windows are 1–5 days, further constrained by backend configuration.
Missing credentials fail explicitly. The full historical command rebuilds the
candidate index automatically unless `--skip-index` is supplied. Rebuild after
standalone CSV/recent imports. Index rebuilding occurs outside map requests;
current memberships are replaced atomically and old candidates remain available
at shared URLs. New observations can legitimately change candidate membership
and generate a new ID; date/sensor/map filters do not regenerate IDs or histories.
Candidates use the existing greedy proximity rule (7 km, 3-day gap, last 15
points, minimum 3 observations), accelerated with spatial buckets. It is not
DBSCAN and does not establish a confirmed wildfire or an official perimeter.

## Read APIs

- `GET /api/v1/italy/coverage`: database counts, products, sensors, dates, last
  import, source configuration, and checkpoints, with historical synthetic records counted separately.
- `GET /api/v1/explorer/clusters?bbox=6.3,35.3,18.9,47.2&zoom=5&scope=italy`:
  Mercator grid aggregation **in SQL**, including the complete matching record
  count, sensor set and observed dates. No 50,000-observation cutoff. Cells split
  with zoom; individual observations can be single-member cells.
- `GET /api/v1/explorer/events`: the same spatial/date/sensor predicates, stable
  indexed candidates, `limit=1..100`, `offset`, and `total_events`. Histories are
  complete; the response does not send all linked detection IDs.
- `GET /api/v1/events/{id}`: persisted candidate history, linked detections and
  available area data. Direct links work independently of explorer filters.

Both explorer queries accept `start_date`, `end_date`, `sensor=MODIS|VIIRS`,
and optional `center_lat`, `center_lon`, `radius_km` (all three together, max 500
km). Exact Haversine filtering executes in SQL after indexed bounds. WGS84
viewport bboxes support the dateline (`west > east`). `scope=italy` uses the import
boundary label when no circle is present; circle searches accept any locally
available geographic dataset. SQLite uses SQL Haversine math. PostgreSQL uses `ST_DWithin` on `geography`
with meters and a matching GiST expression index (PostGIS, as configured by Compose).

Synthetic records are always excluded from explorer results. Empty results mean
no local data is available for the requested area/period; they never prove no fire
occurred. Coverage explicitly reports incomplete geography when a circle crosses
Italy's boundary. Temporal completeness remains unverified even when observations
are present. This intentionally distinguishes observations from coverage claims.

SQLite uses WAL and a busy timeout to support reading during ingestion. Existing
schemas gain the indexed `import_region` column on startup, with existing points
classified against the Italy polygon. Tests always create a temporary database;
their delete fixtures never touch the configured user archive.

## Scientific limits

Imported hotspots without an associated study area have no linked MOD13Q1 or
MCD64A1 observations. Their detail page explicitly reports the missing data.
Recovery requires at least three valid NDVI observations before a recorded
candidate and two after it, of matching observation provenance. No fallback baseline,
trough or midpoint fire date is invented. Baseline is an observed pre-event mean,
not a seasonal model. NDVI cannot establish recovery of biodiversity or forest
structure. Timeline imagery is context; days without observations remain missing.

## Event-scoped MODIS post-fire engine

See [Post-Fire Recovery](../docs/POST_FIRE_RECOVERY.md), [Satellite Pipeline](../docs/SATELLITE_DATA_PIPELINE.md), [Scientific Methodology](../docs/SCIENTIFIC_METHODOLOGY.md), [Analysis Cache](../docs/ANALYSIS_CACHE.md) and [Verification](../docs/POST_FIRE_VERIFICATION.md).

The existing PostgreSQL/PostGIS database and persistent cache volume are reused. Additive tables are initialized automatically; imported FIRMS rows are not reimported or deleted.

Set `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD`, or `EARTHDATA_TOKEN`, in `.env` (backend only). Earthdata must authorize LP DAAC access and applicable EULAs. CMR metadata discovery does not require credentials. Missing/invalid authentication produces a failed job, never synthetic observations. Default cache retention is non-destructive; configure disk limits and optionally explicit source-only LRU according to [cache documentation](../docs/ANALYSIS_CACHE.md).

```bash
docker compose up -d --build db backend analysis-worker frontend
```

Without Compose, run the API and worker as separate processes with the same `DATABASE_URL`, Earthdata configuration and `AFTERFIRE_ANALYSIS_CACHE_DIR`:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
python -m app.jobs.analysis_worker
```

The worker reads credentials from Settings into its own environment for earthaccess; it does not write `.netrc`. A single worker service runs configurable lanes, default one. Restarting containers preserves jobs and sources; expired leases are reclaimed after at most three minutes.

Numerical tests use tiny controlled arrays and georeferenced GeoTIFFs. Tests automatically override the archive database with a temporary SQLite database. To run PostgreSQL tests explicitly provide `AF_TEST_DATABASE_URL` whose database name begins `afterfire_test_`; only that test schema is reset. Never override this safety check.

```bash
cd backend
python -m pytest -q
```

For Python 3.12 Docker with raster/HDF4 dependencies and existing script-based Explorer tests:

```bash
docker compose run --rm --no-deps -v "$PWD/backend:/app:ro" -v "$PWD/scripts:/scripts:ro" backend python -m pytest -q -p no:cacheprovider
```

Run that Compose command from the repository root. Docker installs HDF4 headers and libexpat required by the scientific runtime; a system Python without HDF4 support cannot read native MODIS files. Frontend verification: `npm run build --prefix frontend`, plus the replayable UI checks documented in [verification](../docs/POST_FIRE_VERIFICATION.md).

## Phase 3 — verified pipeline and monitoring

The event status API now includes durable worker phases, cached/downloaded/validated/processed source counts, actual network bytes, rates and persisted timing. SSE: `/api/v1/events/{event_id}/analysis/stream?job_id=...`; Nginx buffering is disabled and the client retains polling fallback. The additive `event_analysis_progress` table is created by init_db without resetting existing data. See [Phase 3 reproduction and evidence](../docs/PHASE3_VALIDATION.md).

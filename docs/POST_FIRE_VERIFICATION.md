# Phase 2 implementation and verification — 28 October 2026

The engine is implemented in the existing AfterFire repository and running in Docker Compose. **A successful end-to-end NASA raster analysis has not been demonstrated: the configured Earthdata credentials are rejected.** Synthetic scientific fixtures passing does not establish real-data correctness in production.

## Audit and archive protection

Read-only PostgreSQL audit found 802,239 non-demo detections across all local records, dated 2000-11-02–2026-10-27, and 46,637 non-demo candidate records. The existing Italian Explorer/current index specifically reports **802,234 Italian observations and 46,629 candidates**, matching the prior implementation report. These are different scopes, not newly downloaded hotspots. No FIRMS import, reindex, deletion or archive reset was run.

The working tree already contained extensive Phase 1 changes at the start. Those changes were preserved. The new engine uses additive tables, the existing DB/session infrastructure, linked candidate detections, existing React Query/Recharts/Leaflet libraries, the existing event URL and the existing persistent cache volume. Legacy area-level engines remain available, while the event page uses event-specific results to avoid attributing whole-study-area vegetation to one candidate.

## Real service attempt

| Evidence | Actual outcome |
|---|---|
| Candidate | `event-4a728489ea44ea85eab6a978870e0b06` |
| Observed interval | 2021-08-11–2021-08-12 |
| FIRMS observations | 262, comprising 33 MODIS and 229 VIIRS |
| Mean coordinates | 37.0142764 N, 14.7733953 E, Sicily |
| Requested vegetation window | 2019-08-11–2021-09-15; pre=2 years, post maximum=1 year |
| Provisional area | Approximately 84.553 km², 1,000 m buffered hotspot footprint; **not measured burned area** |
| Job | `ea98d32ab8e9dc5373f226cdd0df61c0f6dd985e9a2db3d0ccb7ef7fffeb4480` |
| CMR discovery | Real metadata and HTTPS links returned for Collection 061, tile `h19v05` |
| Public catalog records returned | 3 MCD64A1 monthly granules (July–September 2021), 51 overlapping MOD13Q1 composites |
| Advertised catalog bytes | MCD64A1: 2,600,108; MOD13Q1: 4,139,295,657; metadata estimates, **not downloaded bytes** |
| Successfully downloaded granules | **0** |
| Acquired source data | **0 bytes** |
| Real valid NDVI/EVI observations | **0** |
| Real extracted burned cells | Unavailable; zero extraction is not evidence of no burning |
| Initial attempt | 35.13 seconds, published an explicit partial/missing-data report with 98 null index slots |
| Retry | Failed at acquisition, prior partial result preserved; same job/configuration, attempts=2 |
| Repeated request | Returned the same persistent job; no duplicate job created |
| Real source-cache hit proof | **Not possible**, because no NASA source was acquired; source-cache behaviour verified with controlled fixtures |

The initial SDK authentication returned an apparently authenticated object with an **empty access token**, and LP DAAC downloads returned HTTP 400 `Malformed Authorization header`. A direct request to the official Earthdata token endpoint using the configured username/password returned **HTTP 401**, and a cookie/redirect attempt returned **401 HTTP Basic: Access denied**. The downloader now rejects empty tokens immediately and provides an actionable failed state rather than repeatedly requesting every granule. Credentials, authorization headers and token values are not recorded in evidence files.

The final code also excludes composites starting before the requested pre-window or ending after the requested observation cutoff, so only the wholly eligible subset of overlapping CMR holdings is acquired. Catalog counts above record discovery holdings, not a statement that every overlapping composite should be processed. Current CMR processing revisions are used; a historical observation cutoff is not a historical publication-date reconstruction.

Full machine-readable evidence: [real verification](post-fire-real-verification.json), [Explorer regression](post-fire-explorer-regression.json), [browser verification](post-fire-ui-verification.json), [screenshot](post-fire-analysis.png).

## Automated verification

* **45 backend tests passed on isolated SQLite**, including the existing API/scientific/Explorer tests and 15 new event-engine tests.
* **45 backend tests passed on isolated PostgreSQL/PostGIS** `afterfire_test_recovery_20261028`. Test setup refuses database names outside `afterfire_test_*`; the production/archive DB was not reset.
* The final cache-sidecar repair and quarantine retention changes were also rerun with all 15 event-engine tests and passed.
* Numerical fixture evidence includes raw 6,000 → index 0.6; exclusion of out-of-range/cloud/shadow/snow/nonland pixels; cell area using native equal-area pixel dimensions; known seasonal median/MAD/anomaly values; no post-event baseline leakage; recent pre-reburn evidence and explicit insufficient data.
* Tiny controlled HDF4 and GeoTIFF fixtures verify native SDS window reads, grid checks, georeferencing, QA masks, raster statistics, PNG transparency and native GeoTIFF output. A complete controlled pipeline fixture verifies four burned cells, a common analysis geometry, NDVI baseline 0.6, post observation 0.2 and anomaly −0.4. These are **test values**, never inserted into the archive or shown as NASA measurements.
* Cache tests verify hashes, corrupt source/sidecar reacquisition, quota rejection, temporary-file cleanup, active-job eviction protection and one download for two concurrent consumers.
* Queue tests verify same-configuration concurrent requests, durable identity, one active claim, expired-lease reclamation, rejection of stale owners, atomic publication and retention of a previous result after retry failure.
* Provider/API tests cover collection/version/date/tile validation, public discovery, unavailable products, missing credentials, empty SDK tokens, no-source partial results, no job created by GET, and invalid input. Composites extending beyond the requested cutoff remain missing.
* **Frontend TypeScript/Vite production build passed**, including Docker frontend build. Vite reports a large JS bundle warning (approximately 981 kB uncompressed); no build error. Backend warnings concern existing datetime/Shapely/Affine deprecations, not failing scientific assertions.

## Browser and existing Explorer

The replayable [browser test](../scripts/verify_explorer_ui.mjs) passed with:

1. Italy/all-date initial view and numbered clusters.
2. Empty historical date filters removing stale markers.
3. Circle drawing, radius editing and clearing.
4. Empty foreign archive queries and return-to-Italy preserving filters.
5. Server pagination, map selection and stable event URLs after refresh.
6. Explicit acquisition action, no automatic download on page open, and disabled pre/post phases when observations are missing.
7. Mobile Explorer at 390×844 with no horizontal overflow.

Additional event-page checks passed: failed authentication visible, old partial result retained, EVI/NDVI selection, no fabricated before/after image, and discrete date synchronization. Moving 2021-08-11 → 2021-08-12 changed FIRMS map paths from 151 to 113 (including the same analysis outline), while the selected-date chart reference line changed x-position from 1137.003 to 1138.473. Event-page mobile map height was 440 px with document width 384 px in a 390 px viewport. The map geography remains fixed.

The API regression script passed SQL counts, instruments, empty dates, local/foreign circles, partial coverage, pagination and direct event history. No new analysis job was initiated by these Explorer/browser checks except the explicitly clicked retry on the selected real verification candidate.

**Not verified with real acquired rasters:** map raster rendering, actual MOD13Q1 QA distributions/statistics, observed MCD64A1 cell association, real seasonal baseline, real vegetation trajectory, real before/after pair and real source-cache reuse. Their processing code is exercised by controlled fixtures; the real-service boundary remains blocked by authentication.

## Reproduce and unblock

Configure a valid **raw `EARTHDATA_TOKEN`**, or correct `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD`, in the backend `.env`. Verify the account and required LP DAAC authorizations/EULAs. Never paste secrets into frontend configuration or evidence files. Then recreate API and worker to load environment changes:

```bash
docker compose up -d --force-recreate backend analysis-worker
backend/.venv/bin/python scripts/verify_post_fire_real.py --start
backend/.venv/bin/python scripts/verify_post_fire_real.py --catalog
```

Run the final command again after the asynchronous worker finishes; it retrieves actual observations/assets, records valid counts, byte totals and duration, and verifies a repeated request returns the same job. The selected two-year/short-post window is intentionally bounded: a preview of a three-year pre plus one-year post window advertised about 7.02 GiB of MOD13Q1 tiles, exceeding the default 5 GiB job source limit. Whole regional tiles are supported; remote server-side subsetting is not implemented. Reduce windows or deliberately increase resource limits when justified.

## Phase 2 file manifest

| Area | Added or changed by this phase |
|---|---|
| Scientific engine | `backend/app/analysis/modis_science.py` |
| Official provider | `backend/app/providers/modis_catalog.py` |
| Queue, cache, pipeline, rasters | `backend/app/services/analysis_jobs.py`, `post_fire_pipeline.py`, `satellite_cache.py`, `satellite_rasters.py`; `backend/app/jobs/analysis_worker.py` |
| Additive data/schema | `backend/app/models/satellite_analysis.py`, `backend/app/models/__init__.py`, `backend/app/schemas/satellite_analysis.py` |
| API/bootstrap | `backend/app/api/routes/event_analysis.py`, `backend/app/main.py`, `backend/app/db/database.py` |
| Backend configuration/runtime | `backend/app/core/config.py`, `backend/requirements.txt`, `backend/Dockerfile`, `backend/README.md`, `compose.yaml`, `.env.example` |
| Frontend | `frontend/src/pages/EventAnalysisPage.tsx`, `frontend/src/components/charts/RecoveryChart.tsx`, `frontend/src/components/map/EventSatelliteMap.tsx`, `frontend/src/api/satellite.ts`, `frontend/src/types/satellite.ts` |
| Tests and replay | `backend/app/tests/test_post_fire_recovery.py`, `scripts/verify_post_fire_real.py`, `scripts/verify_explorer_ui.mjs` |
| Documentation/evidence | `README.md`, `docs/POST_FIRE_RECOVERY.md`, `SATELLITE_DATA_PIPELINE.md`, `SCIENTIFIC_METHODOLOGY.md`, `ANALYSIS_CACHE.md`, this report and the four linked evidence artifacts |

No separate application, generic satellite demo or fabricated production observation was created. Published scientific results are retained by default; source-only eviction requires an explicit policy. Descriptive status thresholds are operational conventions, not validated ecological recovery criteria. See [methodology](SCIENTIFIC_METHODOLOGY.md), [pipeline](SATELLITE_DATA_PIPELINE.md), [cache](ANALYSIS_CACHE.md), [API/user flow](POST_FIRE_RECOVERY.md).

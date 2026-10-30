# Phase 3 — scientific validation, satellite maps and live analysis

Verified on 28 October 2026. No Phase 4–7 features, historical reimport, database reset or synthetic production observations were introduced. Existing uncommitted work was preserved.

## Real scientific result

The full event → durable worker → NASA source cache → HDF4 → QA → native raster → scientific result → PostgreSQL → API → browser path was exercised.

- Event: `event-4a728489ea44ea85eab6a978870e0b06`, Sicily, 11–12 August 2021, approximately 37.0142764 N / 14.7733953 E. Database/API confirm 262 associated observations: 33 MODIS and 229 VIIRS. Tile `h19v05`.
- Database audit: 803,761 total detections, including **802,234 real Italy detections**; 46,657 total candidate events (46,637 real, 20 demo). The total includes records outside the real Italian archive; these counts must not be conflated.
- Engine: `modis-recovery-2.1.0`; job `bdb63b007ba77f798707fa0a1727b338348ccba31cd049862860ef390d5e2ea8`.
- Requested observations: 11 August 2019 through 15 September 2021, pre_years=2, post_years=1, buffer=1000 m, QA coverage threshold=0.5.
- Sources: **48 MOD13Q1.061 + 3 MCD64A1.061**, all `h19v05`. The complete 51-file manifest, exact original names, sizes, SHA-256 hashes and band metadata are in [numerical evidence](phase3-numerical-verification.json) and [source validation](phase3-source-validation.json).
- Actual source volume: **3,890,398,220 bytes** (3.6232 GiB); all 51 sources reused, **0 new download bytes**. Catalog estimate was 3,890,397,854 bytes, explicitly separate from measured file sizes.
- All files passed SHA-256/size checks, internal granule identity, Collection/tile identity, native sinusoidal georeferencing and SDS dimension/calibration checks. HDF4 bands were read and the event windows processed. Local SHA-256 checks verify unchanged acquired files; these are not claims of comparison with a NASA-published checksum.
- **98 persisted index rows** across 49 expected composite dates: **44 valid NDVI + 44 valid EVI**, **10 missing index values**, with no interpolation. Of each index's valid observations, 41 are wholly pre-event, 1 overlaps the event and 2 are post-event.
- **94 quality-screened MCD64A1 cells**, **20.1779152898568 km²**, zero ambiguous cells. No hotspot-circle area was substituted for burned area.
- Latest post-event composite: **29 August–13 September 2021**. NDVI **0.2521**, seasonal anomaly **−0.23635**; EVI **0.1285**, anomaly **−0.15675**. Both are below seasonal baseline. No ecological recovery claim is made.
- Result status: **partial**, correctly reflecting missing/QA-rejected composites. Source acquisition and scientific processing finished; `partial` does not imply that every requested date had usable data.

An independent verification script re-read all source files, recomputed **96 raster index checks**, checked **6 post-event seasonal-reference rows**, compared all persisted observation rows, checked burned-cell count/area and verified native GeoTIFF values and nodata. Only floating point round-off tolerance (1e-12 for double statistics, 1e-7 for float32 GeoTIFF) was allowed. Evidence: [phase3-numerical-verification.json](phase3-numerical-verification.json).

## Scientific definitions and QA

MOD13Q1 indices are the product's already-computed vegetation indices; AfterFire scales them rather than recomputing them from unavailable red/NIR bands. HDF metadata stores a divisor `scale_factor=10000`; the applied conversion is **index = raw / 10000 = raw × 0.0001**, with zero offset. Raw valid range is −2000…10000; fill −3000 is excluded.

The strict mask requires reliability=0; MODLAND QA bits 0–1=0; VI usefulness bits 2–5≤2; aerosol bits 6–7<3; bits 8,10,14,15 clear; land class bits 11–13=1. Selection uses native pixel centres inside the analysis geometry. A composite statistic is the median of valid pixels only, published only when valid_pixels / expected_native_pixels ≥ configured threshold (0.5 here). Spatial spread is population standard deviation of the valid scaled pixels. Missing and incomplete-period composites remain null.

For MCD64A1, bits 0 and 1 must both be set, shortened-mapping bit 2 must be clear, burn DOY must be valid for the year, uncertainty must be 0…100 days, and the burn-date uncertainty interval must intersect the FIRMS event interval extended by ±3 days. Native cell centres must intersect the candidate's metre-buffered territory. Cells overlapping competing event candidates are explicitly ambiguous and excluded when selecting the vegetation analysis area. Cell area is **abs(pixel_width × pixel_height) / 1e6**, about 0.214659 km² for the native 463.313 m grid; 500 m is the nominal product resolution. Monthly duplicate cells are deduplicated by geometry and burn date. These are observed grid cells, not official fire perimeters.

The seasonal reference is the median of valid, wholly pre-event composites within ±24 circular calendar days of the target date, mapped to leap reference year 2000. It requires ≥3 composites spanning ≥2 distinct reference years. Pre-event chart points use only still-earlier composites. Anomaly = observed spatial median − seasonal median. MAD = median(abs(reference values − seasonal median)); reference band = median ± max(0.05, 1.4826 × MAD), a robust spread envelope, not a confidence interval. Status thresholds are +band (above), −band (near), −2×band (approaching), otherwise below seasonal baseline. Null observation/reference means insufficient data.

Primary specifications: [NASA MOD13 user guide](https://landweb.modaps.eosdis.nasa.gov/data/userguide/MODISC6VIUserguide.pdf), [MCD64A1 Collection 6.1 user guide](https://lpdaac.usgs.gov/documents/1006/MCD64_User_Guide_V61.pdf), [NASA MCD64A1 file specification](https://ladsweb.modaps.eosdis.nasa.gov/filespec/MODIS/6/MCD64A1).

## Real worker progress

`event_analysis_progress` is an additive JSON telemetry table keyed to the existing unique job. API and worker initialization create it without changing/deleting FIRMS tables. Writes are fenced by the worker owner and active job state. Explicit retries clear attempt telemetry while retaining previous published results; automatic expired-lease replay retains the original start timestamp and records previous-attempt transferred bytes separately.

The actual order is preparation → CMR discovery → acquisition/processing of MCD64A1 → acquisition/processing of MOD13Q1 (including QA and per-composite map assets) → seasonal baseline → recovery indicators → atomic publication. Acquisition and processing are interleaved by granule: the UI does not pretend that all downloads finish before processing starts.

Overall progress reserves 0–5% for preparation/discovery, 5–85% for two real work units per source (acquisition and scientific processing), 86% for time-series/baseline work, 93% for indicators and 97% for publication. Work within the source phase is `5 + floor(80 × completed_units / (2 × discovered_sources))`. Active values are capped at 99%; only the database publication transaction sets 100%, together with the result. Failures retain progress/counters. An all-null analysis without observed burned cells fails rather than claiming successful completion.

- Files: discovered/total from completed CMR discovery; cached/downloaded from acquisition; validated from HDF checks; processed from successful scientific granule work; acquisition/validation and scientific failures are separate counters.
- Actual transfer bytes come from received downloader blocks, including blocks received before a transfer failure; **cache hits never increment network bytes**. Cache volume comes from verified on-disk sizes. Result bytes measure serialized scientific JSON, not the total size of derived PNG/TIFF assets.
- Network updates are throttled to approximately one database write per second, with operation boundaries/failure flushing the current counters. Current speed is measured bytes/monotonic interval; recent speed uses EWMA `0.3 × sample + 0.7 × previous`. No artificial UI progress timer exists.
- Elapsed time is computed server-side from persisted start/finish timestamps, frozen at terminal state. Refresh and completed-result Docker restart retain the same elapsed/start times.
- Current-phase ETA uses elapsed phase time / finished granules × remaining granules. It is exposed separately because it excludes later baseline/publication work. **Whole-job ETA remains null / “Remaining time unknown” when subsequent work has no measured duration**; it is never extrapolated from download speed alone. At publication remaining time is zero. Estimates update on observed completed work, not a fabricated countdown.
- `completed`, `partial` and `failed` remain distinct. Cancellation is not supported and is not offered.

Existing status endpoint: `GET /api/v1/events/{event_id}/analysis/status` (optional job_id). Added SSE endpoint: `GET /api/v1/events/{event_id}/analysis/stream?job_id=...`. The stream reads persistent worker telemetry using fresh database sessions; it releases sessions between updates. EventSource reconnects automatically; 2.5-second React Query polling is a fallback and refresh recovery. GET never creates a job. Nginx buffering is disabled. Existing idempotent POST `/analysis` remains authoritative. `result_job_id` explicitly identifies a previous valid result when a newer job is active or fails, keeping it accessible in the frontend.

[Captured first real SSE progression](phase3-progress-stream.log) and [final cache replay with phase ETA](phase3-progress-replay.log) includes cache growth, source processing and final publication; the first real reprocessing run took about 78.8 seconds. Transfer bytes/rate under an actual new NASA network download were not re-tested because all valid files were already cached; transfer accounting/rate/error behavior was tested with controlled byte streams.

## Satellite maps

A shared `SatelliteBasemap` serves both map hosts, `LeafletMap` (Explorer and Territory) and `EventSatelliteMap` (event timeline and both Before/After maps). Recovery, Recurrence and Compare currently have no independent Leaflet initializations; any map composed from these hosts inherits the same basemap. Frontend-wide searches found no remaining street-map defaults or street-map fallbacks.

Provider: **Esri World Imagery**, a global satellite/aerial imagery service; Web Mercator JPEG tiles at the documented public ArcGIS REST endpoint. No key was required for the public endpoint during these tests. Attribution uses current item credits: **Esri, Vantor, Earthstar Geographics and the GIS User Community**, with a source/terms link. Coverage/resolution/acquisition date vary by location. Native zoom is capped at 19, with overzoom rather than unsupported higher native tile requests. An imagery error notice replaces any need for a silent street fallback. No offline tile exporting was added.

Terms were checked against the official item metadata and saved in [provider evidence](phase3-basemap-provider.json): this is Esri licensed content, not public domain; the item disallows using this layer for offline export. No unlimited request allowance or service availability guarantee is claimed. See [World Imagery](https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9) and its linked terms. The satellite background is explicitly geographic context with variable/unknown date, separate from dated FIRMS, MCD64A1 and MOD13Q1 overlays. Optional dated NASA GIBS true-colour context remains an imagery overlay, not a road fallback.

Actual browser checks confirmed loaded satellite tiles and loaded MOD13Q1 PNGs in all three event/comparison maps, four chart curves, displayed NDVI 0.252 and coverage 364/376 (96.8%), matching API values. Explorer regression covered clusters, date/sensor filters, drawing/editing/clearing the circle, New York navigation and return to Italy, candidate selection, pagination, no automatic acquisition and direct event refresh. A 390×844 viewport had no horizontal overflow on event or Explorer pages. Evidence: [event UI](phase3-event-ui.json), [Explorer UI](phase3-explorer-ui.json), [live screenshot with measured phase ETA](phase3-live-progress-final.png), [mobile screenshot](phase3-mobile.png), [final satellite result](phase3-satellite-result.png).

## Tests and reproduction

Fixture tests are separate from real NASA evidence. **52 tests passed on isolated SQLite and 52 passed on isolated PostgreSQL/PostGIS**, including metadata integrity, HDF4 reads, QA/scaling, native raster generation, baseline, persistent queue/reclaim/idempotence, transfer accounting, cache distinction, elapsed time, phase ETA/unknown whole-job ETA, terminal SSE/reconnection and prior result retention. PostgreSQL tests use only `afterfire_test_phase3_20261028_1430`; the test guard rejects any database without the `afterfire_test_` prefix. Logs: [SQLite](phase3-tests-sqlite.log), [PostgreSQL](phase3-tests-postgres.log). Vite/TypeScript production build passes, with the existing large-bundle warning. Python dependency deprecation warnings remain.

The API check was repeated **through the frontend Nginx proxy after container recreation**: persistent source volume, scientific result, raw observation API equality, asset downloads, terminal SSE reconnect, stable elapsed time and idempotent reuse all passed. Evidence: [API verification](phase3-api-verification.json). The real archive counts remained unchanged. The final replay captured 55 SSE frames with monotonic overall progress, including 54 frames with measured phase ETA. A subsequent restart preserved the exact scientific-result SHA-256, job id, start timestamp and elapsed time.

Reproduce without any new NASA downloads:

```bash
# Existing services/volumes only; do not use down -v.
docker compose up -d --build

docker compose cp scripts/verify_phase3_api.py backend:/tmp/verify_phase3_api.py
docker compose exec -T backend python /tmp/verify_phase3_api.py --base http://frontend:3000

docker compose cp scripts/verify_phase3_science.py backend:/tmp/verify_phase3_science.py
docker compose exec -T -e PYTHONPATH=/app backend python /tmp/verify_phase3_science.py

# Tests use conftest's isolated database, never the archive. Import tests need /scripts.
docker compose cp scripts backend:/scripts
docker compose exec -T backend python -m pytest app/tests/ -q --disable-warnings
```

For an explicit cache reprocessing run, POST `/api/v1/events/event-4a728489ea44ea85eab6a978870e0b06/analysis` with `{"configuration":{"pre_years":2,"post_years":1,"as_of":"2021-09-15"},"retry":true}` and subscribe to its returned id via SSE. Omitting retry or using false reuses the publication without another attempt. Other periods may require additional authenticated NASA acquisitions and may exceed the configured 5 GiB source limit; the longer default window's earlier quota failure is not evidence of a scientific raster failure. A smaller already-cached configuration was used for validation.

## Files changed in this phase

Backend: `app/analysis/modis_science.py`, `app/schemas/satellite_analysis.py`, `app/models/satellite_analysis.py`, new `app/services/analysis_progress.py`, `app/services/analysis_jobs.py`, `app/services/post_fire_pipeline.py`, `app/services/satellite_cache.py`, `app/jobs/analysis_worker.py`, `app/api/routes/event_analysis.py`, `app/tests/test_post_fire_recovery.py`, new `app/tests/test_analysis_progress.py`.

Frontend: new `src/components/map/SatelliteBasemap.tsx`, `src/components/map/LeafletMap.tsx`, `src/components/map/EventSatelliteMap.tsx`, new `src/components/analysis/AnalysisProgressPanel.tsx`, `src/pages/EventAnalysisPage.tsx`, `src/types/satellite.ts`, `Dockerfile`.

Verification: new `scripts/verify_phase3_science.py`, new `scripts/verify_phase3_api.py`, `scripts/verify_explorer_ui.mjs` (explicit desktop viewport for reproducible coordinate checks), the evidence files linked above and the existing documentation linked below. Other pre-existing worktree changes belong to earlier work and were not attributed to Phase 3.

## Limits

One reference event has sufficient data for both products and was numerically verified; no alternative event was needed. No contemporary basemap is treated as historical imagery. Two post-event composites do not establish long-term ecological recovery. Whole-job ETA remains explicitly unknown until sufficient duration evidence exists. Live new-network NASA download speed has fixture verification only in this run; no unnecessary re-download was triggered. Active-worker crash recovery is covered by lease tests; the real Docker restart check concerned completed results. No other roadmap phase was implemented.

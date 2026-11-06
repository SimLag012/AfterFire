# Clean installation real verification — 2026-11-06

## Verified

- Docker rootful daemon; four clean-install services running. Administration uses OS authorization, with no docker-group or socket-permission change.
- PostgreSQL/PostGIS 3.3: 22 public-schema tables after application initialization, initially zero detections and candidates. Only the selected real candidate was later persisted; no archive import.
- Startup failure diagnosed: the old Unix-socket pg_isready check accepted the temporary init server. The check now requires TCP localhost and actual container user/database. Clean backend has an HTTP readiness check; frontend waits for it and startup uses Compose --wait.
- API and frontend HTTP checks pass on localhost. FIRMS availability authenticates and returns 12 products.
- Google Cloud CLI 592.0.0 installed; ADC created by owner browser login, quota project assigned to the existing project, credentials read-only in both server containers. Both server probes pass for native MOD13Q1/MCD64A1 arrays and QA; 6240 decoded bytes each, no HDF or AppEEARS.
- 186 SQLite tests passed in 22.95 s; 186 PostgreSQL/PostGIS tests passed in 37.22 s. Test database `afterfire_test_clean_20261106` is separate. Production provider settings were excluded only from the regression subprocess, matching the SQLite fixture environment. Scripts needed by CLI tests were temporarily copied into /tmp; none was used for bulk import. Deprecation warnings remain.
- First real non-Italian candidate: `global-d77c8ac8d89369a61e7125f78cfe2e76`, 30 FIRMS MODIS observations, July 2023, Rhodes. [Measured result](clean-api-first-analysis.json): 33.22 s pipeline, 41.331 s request-to-result, 1,991,732 decoded bytes, 71 sources. NDVI/EVI, QA, seasonal baseline and 134 burned cells published. Partial status preserves missing/QA-rejected composites. Repeat Analyze: same job/attempt, 0.03174 s.
- Browser: saved Recovery Story visible, immediate-post-fire frame loaded through lazy generation. No horizontal overflow at 880 px or 390 px; scientific raster loaded at both widths. Recovery Intelligence computed and published from the saved observations: supported below-reference evidence, 21/23 composites, 91.3% completeness. Viewport override reset afterward.

## Storage measured before the real science run

Images occupy 2.696 GB shared total. Backend and worker tags each report 1.77 GB but share almost all layers; do not add them as unique storage. Frontend 96.3 MB; PostGIS 828 MB. Volumes: PostgreSQL 113.7 MB, cache 137.2 kB. Build cache 2.257 GB (about 2.161 GB reported reclaimable); no prune was performed. Later scientific/cache/test data increase the volume totals. These images are functional, not claimed minimal.

## Remaining limits

A single real historical event does not establish global coverage, p95 performance or exact equivalence to deleted historical HDFs. Recent-event, multi-continent, antimeridian live queries and full browser navigation matrix have not been rerun in this installation. Broad Explorer viewports require zooming within provider bounds; unsupported periods and provider outages must remain explicit. Some legacy navigation pages still point to preset area identifiers; use Explorer and selected candidate pages for the clean on-demand flow. Reburn was also verified for 2021-07-21–2024-07-22: 31.68 s, 314160 downloaded bytes, partial state, two observed episodes but zero repeated cells; classification insufficient_evidence. Ten months have incomplete cell mapping, no months entirely missing and no source failures. This does not establish recurrent burning or absence of recurrence. Full Phase 6.5/7 acceptance is not claimed.

# Unified Explorer implementation — 14 November 2026

Local branch: `feature/fire-activity-intelligence`. Starting commit: `1684671b2512ef17155dc54c9e228106805f9564`.
This report separates working software from scientific domains that have not passed independent validation. No push, PR, merge, release or remote deployment is authorized or performed.

## Preservation and architecture

The earlier unified-Explorer work saved 254 modified/untracked files in `/home/simlag012/.codex/backups/afterfire-unified-20261114/working-tree.tar.gz`, alongside the tracked binary patch, status and complete local Git history bundle. The pre-existing four modified documentation files and unrelated evidence are excluded from task commits.

The current synchronization baseline is **167 EventAnalysisResult publications, 20 RecoveryAssessmentRecord publications, and 5 ReburnHistoryRecord publications**; the earlier baseline contained 19 assessments. Baseline payload SHA-256 fingerprints are in `unified-explorer/recovery-before.json`; publication payloads include their published geometries, QA, baseline, classification and vegetation series. File-level source changes remain confined to the activity subsystem and UI integration; no Recovery formula/provider/geometry algorithm changes are made.

Explorer is the primary GIS workspace. A visible, resizable desktop Fire Activity Calendar sits beside the map. On mobile its named toolbar control opens a bottom sheet. Returning from an event with a selected historical month reopens that context. Calendar/chart code remains a separate lazy bundle. Opening the workspace fetches metadata and cached studies, never a POST for 26 years of history.

The original Recovery Story, before/after maps, NDVI/EVI timeline, Recovery Intelligence, Reburn/Recovery Gap, downloads and scientific comparisons remain event-scoped. Comparisons are now accessible from a collapsible event section; assessment selections preserve the event return URL. No scientific publication is deleted.

## Routes and navigation

| Previous route | Current behavior |
| --- | --- |
| `/`, `/explorer` | Unified map workspace |
| `/recovery`, `/recurrence`, `/compare` | Replace-history redirect to Explorer; an explicit event ID redirects to that event |
| `/compare?assessment=...` | Resolve a persisted assessment to its original event, retaining all assessment IDs |
| `/recovery/:areaId`, `/recurrence/:areaId` | Preserve area ID in Explorer, focus saved area, link its retained area report |
| `/events/:eventId/reburn` | Original event story with `view=reburn`, anchored to its existing Reburn section |
| `/datasets` | Explorer Data & Sources panel |
| `/events/:eventId`, `/territory/:areaId`, `/report/:areaId` | Existing event and saved-report URLs remain supported |

Only Explorer remains in the primary navigation. Data & Sources explains NASA products, provenance, processing and the independent Recovery methods. Legacy page source files are retained for dependency/history safety rather than deleted indiscriminately.

## Territory, acquisition and continuity

Requests accept bounding boxes, geodesic circles, and valid WGS84 GeoJSON Polygon/MultiPolygon, including holes. The UI accepts custom coordinates/GeoJSON and displays its geometry. Provider retrieval remains bounded to the source bbox; circle membership uses exact WGS84 geodesic distance and polygon membership uses the supplied shape. Circle area uses a 180-vertex geodesic boundary approximation. This differs from the old circle-bbox behavior, so shape-scoped checkpoint identities include the selection and never alias the old bbox study.

A direct Aqua value describes occupied 10 km cells containing selected detections. Boundary cells are not fractional burned area, and a small AOI does not imply subpixel precision. Unvalidated shape conversions are null. Original normalized records retain their NASA dictionaries and product versions; SP and NRT remain distinct.

Acquisition uses persistent, atomic source CSVs and independently committed activity windows. Resume reads the exact server configuration, including original boundary dates and geometry. It does not use the last unrelated local-storage request. Pause fences the worker lease; completed windows remain available. Status reports actual requested/acquired/missing/unavailable product windows and the last update, rather than fabricated progress.

History checks the same due/expired Recovery states as the existing scheduler before each checkpoint. A future deferred Recovery retry does not create a busy history-yield loop. Each historical acquisition window has a 45-second scheduling budget, including waiting for source locks. Cancellation removes its temporary CSV; completed cache files are preserved. File locks deduplicate identical windows across processes, and two shared transfer slots bound concurrent activity downloads. Quota is checked before each uncached transfer; the existing 500-transaction reserve and NASA limits are unchanged. These are scheduling guarantees, not a measured worst-case production Recovery latency under every load.

Default five-day queries and 28-window explicit batches remain bounded. The source cache retains a 512 MiB cap (with headroom for both transfers); the activity observation store has its separate configurable 512 MiB default guard. This is not an unlimited global archive or a storage lifecycle service.

## Official sources checked

The [FIRMS Area API](https://firms.modaps.eosdis.nasa.gov/api/area/) accepts bbox requests of 1–5 days and documents the shared 5,000 transactions/10-minute limit. The [official archive service](https://firms.modaps.eosdis.nasa.gov/download/) offers region/time exports with Earthdata or email authentication; it is an alternative requiring its own request lifecycle, not an unattended global-download replacement implemented here. No email is sent and no global archive is downloaded.

NASA lists Terra from 1 November 2000 and Aqua from [3 July 2002](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_MODIS_Firehotspots.html). August 2002 remains the first complete reference month. The archive lists S-NPP from 20 January 2012 through 2 November 2026, NOAA-20 from 1 April 2018, and NOAA-21 from 1 March 2023. Live per-product SP/NRT limits are retained in the source snapshot; dates are not inferred from launch dates. [NASA LAADS](https://ladsweb.modaps.eosdis.nasa.gov/alerts-and-issues/199913) confirms the November 2026 S-NPP transition. An unvalidated NOAA replacement is never substituted into its harmonized series.

The user-supplied Space Apps challenge URL returned HTTP 502 during this session. No new challenge text is claimed verified from that page.

## Scientific validation and actual coverage

The original content-addressed calibration is preserved. The multiscale experiment uses only retained authentic pilot CSVs and **no NASA downloads**: six fixed nested square supports (0.05°, 0.1°, 0.25°, 0.5°, 1°, 2°), six original regions, January/August 2019–2024. All nested samples retain the same geographic and temporal folds. Independent raw-coordinate projections match each aggregate. Positive-activity support gates were specified before fitting.

Results: 0.05°, 0.1° and 0.25° have insufficient positive activity; 0.5° and 1° fail the unchanged independent validation gates. Only the original 2° support passes. All coefficients, MAE/RMSE/bias, coverage and positive-support counts—including failures—are in `unified-explorer/scales/calibrations.json`. **No small-scale conversion is released.** This experiment provides evidence against applying the regional coefficient indiscriminately.

An additional fixed seasonal campaign covers all twelve months in 2021, 2023 and 2024 for the same six regions, reusing the original pilot observations. Design and gates are written before retrieval. Training adds 2021; 2023 calibrates intervals; 2024 and the two excluded geographic regions remain separate tests. Per-month holdout gates must pass in addition to pooled gates. A reviewed supplementary artifact can enable only passing months, with separate year ranges and exact square-support constraints. The original pilot remains the fallback. A candidate artifact is never installed automatically by the acquisition script.

**Seasonal campaign finished: 252 authentic region-month pairs, 292,401 original records. The pooled model failed validation and no seasonal coefficient was installed.** All twelve calendar months were acquired in 2021, 2023 and 2024, alongside the original January/August 2019–2024 pilot. Additional land-cover/biome strata and Terra/Aqua, NOAA-20/21 and SP/NRT transition calibrations remain unsupported. Original observations and explicit gaps implement the correct behavior in these domains.

The calendar distinguishes missing, partial, verified-query zero, unsupported conversion and provider failure. Same-month anomalies exclude the target year and require five complete comparable years with the same calibration identity. Annual totals reject mixed conversion regimes; annual trends require eight complete direct-reference years. Newly acquired July 2021 Sardinia has 1,913 original records and 20 observed Aqua cell-days; its VIIRS conversion and anomaly are unavailable with the current published model/history. This is a coverage expansion, not evidence that a conversion passed.

## Tests and performance

Evidence and final counts are recorded under `unified-explorer/`. The initial existing SQLite suite passed 126 tests; after geometry/scheduling safeguards, PostgreSQL/PostGIS passed 130. Final reruns include additional transfer-cancellation, annual-regime and artifact-validation tests; see the retained final logs.

Independent replay of nine selected existing publications from retained raster sources passes (`recovery-native-after.json`). This does not claim all-publication raw-raster replay. The current rerun is `sync-native-replay.json`. All-publication payload fingerprints are checked separately. Browser tests use the production build, actual local APIs and acquired NASA data; development hot-reload failures are excluded from production verification and corrected by reloading the built application.

Current browser evidence, screenshots, CSV consistency, timing, archive/cache sizes and limits are recorded in the synchronization section below.

## Acceptance and remaining work

The unified UX and supported acquisition/scientific states are implemented. Full historical acquisition is incremental and quota/storage limited; no complete 2000–today archive is asserted. All-season calibration, multi-scale conversion, transition stability, new geographic/biome representativeness, long annual trends and automatic historical archive-export ingestion require independent evidence before acceptance. Failed scale tests are retained rather than relaxed.

## Files and local commits

Task changes cover the activity schema/service/routes/provider/science/tests; Explorer layout, calendar, map selection rendering, app redirects, navigation/footer and event comparison entry; the two validation scripts and this report plus the three requested activity documents. The exact task manifest and local commit SHAs are recorded after staging review. Existing unrelated user files remain unstaged. Publishing requires the owner to review the remaining scientific criteria and local commits, then decide independently on push, merge and release. No publication command or PR is executed by Codex.

## Remote frontend synchronization and completed verification (14 November 2026)

`git fetch origin` retrieved **f67ba4f**, `feat(ui): redesign AfterFire interface and tokens for hackathon review`, on top of remote **99e3a04**. All frontend changes from that commit were integrated by a three-way content merge against its parent. Conflicts were resolved in favor of the new visual tokens, navigation layout, event presentation and map controls, retaining the unified Explorer routes, calendar, exact selection and event return context. This intentionally preserves the local pilot commits descended from **ac02204**; no main checkout, remote update, PR or deployment occurred.

Before this synchronization, **383 modified/untracked files**, the complete local history bundle, working-tree binary patch and refs were saved in `/home/simlag012/.codex/backups/afterfire-sync-20261114-152905` (55,737,247 bytes at capture). The earlier backup is retained too. Existing Windows portability changes, local runtime launcher and unrelated historical audit reports are preserved outside task commits.

The desktop calendar and the single mobile calendar action now use the remote design tokens. Both empty and cached calendars display every year from 2000 through the current year. Comparisons reject null measurements and different calibration identities. Recovery Intelligence keeps a visible event heading. Browser testing reproduced a Leaflet 1.9.4 zoom-transition callback firing after map removal when opening an event or replacing a selection. Both map components now use the public `zoomAnimation=false` option, avoiding that stale transition while retaining pan, zoom and touch selection. The final production-browser run has no JavaScript errors.

### Actual scientific results

| Experiment | Result |
| --- | --- |
| Pooled all-month fit, 72 training / 48 interval / 48 temporal / 84 geographic units | Coefficients `[0, 0.7509136050942067]`; rejected |
| Pooled temporal holdout | MAE 16.2071; RMSE 45.0432; bias −11.5461; relative bias −36.0816%; interval coverage 77.0833% |
| Pooled geographic holdout | MAE 16.5834; RMSE 32.8119; bias −0.6957; relative bias −1.7096%; interval coverage 67.8571% |
| Exploratory calendar groups `[12,1,2]`, `[3,4,5]`, `[6,7,8]`, `[9,10,11]` | December–February fails; March–May and September–November lack the unchanged minimum calibration support; June–August passes aggregate gates, with only June/August passing monthly gates |
| Frozen summer candidate confirmed on previously unseen June 2022/2025 | 12 additional independent region-month pairs; 9,174 original records; **rejected** |
| June confirmation, seen regions / unseen years | MAE 18.6788; RMSE 30.8047; bias −11.5112; relative bias −25.0243%; coverage 100% |
| June confirmation, geographic holdout / unseen years | MAE 7.0229; RMSE 8.1477; bias +7.0229; relative bias +43.2180%; coverage 75% |

Calendar groups describe months, not equivalent physical seasons or biomes across hemispheres. The confirmation design froze candidate ID, coefficients, interval width, held regions, years and acceptance gates **before retrieving the new samples**. No fitting, threshold adjustment or month substitution followed its failure. The pooled and exploratory artifacts remain evidence only. The content-addressed January/August pilot remains the only released VIIRS conversion. Direct observed Aqua cell-days and original mission records are available across acquired months without pretending a conversion is supported.

Combined campaigns cover **264 distinct region-month pairs and 301,575 source records**. The six 2019–2025 study views each expose **44 complete Aqua reference months out of 84 requested**, with gaps retained; older 2019–2024 study views expose 43/72 because the new June 2022 checkpoint is shared. Original 2025 June observations extend actual coverage beyond the pilot. None of these partial studies is described as a complete multi-decade archive. `season-publication.json` records the earlier 42/72 snapshot; `june-confirmation/publication.json` records the later 44/84 views. Publication is cache-only and refuses uncached NASA transfers.

A separate real small Sardinian selection acquired **November 2000**, in three batches of two MODIS product windows. Pause and resume retain completed checkpoints; the final status records six acquired windows, 36 windows outside product availability, six NRT windows skipped in favor of SP, zero missing windows and 100% completion. Re-enqueue returns the completed study. Original counts remain available and Aqua-equivalent activity is null (`reference_not_yet_available`), rather than a fabricated zero or an unvalidated Terra bridge. Evidence: `sync-history-acquisition.json`.

### Tests, performance and preservation

Production UI at `http://127.0.0.1:3000` uses the rebuilt local frontend/API/worker and the existing database/cache volumes. Browser checks at **1440×900** and **390×844** verify actual map tiles, immediate calendar access, single navigation, cached Italian months and anomalies, month changes, native touch-circle drawing, original event links, Before/After, Recovery Intelligence, Reburn/Recovery Gap, event return preserving study/month/circle, legacy event redirects and Data & Sources. No history POST is issued by this read-only exploration. Evidence and screenshots: `sync-browser-verification.json`, `sync-desktop.jpg`, `sync-mobile-calendar.jpg`, `sync-mobile-circle.jpg`, `sync-desktop-recovery.jpg`, `sync-mobile-recovery.jpg`. The reproducible script requires a separately installed Playwright/Chromium runtime; it never substitutes API responses.

The current SQLite and isolated PostGIS suites, independent CSV/API checks, warm HTTP timing, local process/cache telemetry, secret scan and final preservation comparisons are recorded in the `sync-*` evidence files. CSV verification reprojects authentic original coordinates, checks exact circle/polygon membership where applicable, recomputes occupied cell-days and conversion intervals independently, verifies leave-target-year-out anomalies and rereads the calendar to prove exports do not change it.

The synchronization baseline fingerprints all **167 / 20 / 5** persisted scientific payloads. It additionally hashes **39,064 retained raster/array/image files totaling 229,392,829 bytes**. The independent native-raster replay passes for **nine selected publications**, checking vegetation values, geometry/burned cells, QA support, baseline and related saved assessments/histories. This scope is distinct from checking every publication JSON and every retained raster file; it is not a claim to replay all 167 analyses from NASA.

Performance evidence distinguishes local warm reads from fresh acquisition, browser navigation from provider latency, and measured idle resource use from unmeasured stress behavior. A 45-second acquisition checkpoint bound and Recovery-first scheduling are tested; a live worst-case Recovery queue latency under sustained history/provider load is **not measured**. Session-wide NASA transaction totals and CPU peak throughout all acquisition were not instrumented and are not reconstructed from current quota counters. Current provider availability/quota snapshots and bounded acquisition window counts are retained instead.

### Acceptance still open

Universal all-season VIIRS translation, new representative biomes/regions, reliable conversion for arbitrary local scales/shapes, Terra→Aqua and NOAA/SP/NRT mission bridges, complete 2000–today acquisition, long-term reprocessing refresh and archive lifecycle, and a production-load Recovery latency bound remain open. Calendar observations, anomalies where comparable history exists, supported pilot conversions and explicit gaps are operational. Failed validation evidence is retained; these requirements are not marked complete.

Exact task files, final check results, local commit SHAs and remaining unstaged user files are listed in `sync-delivery.json` and the local commit history. Publication requires owner review of the scientific limits, then the owner's own push/merge/release decisions. No remote publication is part of this work.

Final measurements: **293 SQLite tests and 293 PostGIS tests pass**. Five authentic study exports independently verify **8,643 original records**, **89 Aqua cell-day values**, **24 converted values/intervals** and **24 supported anomalies**, including a real polygon (35 observations), geodesic circle and Terra-only November 2000. All **192 scientific publication payloads** (167+20+5) and **39,064 raster/array/image files** are unchanged; native replay of nine selected publications passes.

The production-browser script passes **15 scenarios**, including redirects for two authentic saved assessments, with no JavaScript errors, overflow or automatic history acquisition. On this local run, map/calendar/first basemap tile are ready after **717 ms**; opening the mobile calendar takes **152 ms**. Five warm calendar reads have medians **146.1 ms** for an 84-month view and **10.8 ms** for the small circle month. The measured cache has **166,218 files / 409,434,698 bytes**, including **3,703 source CSVs / 27,895,094 bytes** shared with FIRMS use. These counts describe the captured inventory, not session-wide NASA transactions or peak resource use. The resource snapshot records approximately **141.4 MiB API**, **118.4 MiB worker** and **8.0 MiB frontend**; PostgreSQL had background test/publication activity, so its CPU sample is not an idle baseline. The 35-observation polygon study verifies exact membership and partial-month null activity; its SP observations can reuse a verified enclosing query with the same bbox without another transfer.

Source implementation commit: **`fbc3659acef60c7dd37e3345c60bd9b06054c202`**. This report and its evidence are delivered in the following local documentation commit; its SHA is available in `git log` and the final response. Existing unrelated Windows/runtime/audit edits remain in the working tree. The activity provider stages native Unix `fcntl` as before, while the pre-existing Windows lock-adapter import remains an unstaged user change; the adapter exports the same native functions on this tested Linux host. Final scoped secret scan: **415 text files, zero findings**, covering configured credential values and known token/private-key patterns; it is not an entropy scan.

A final native Chromium mouse-drag check confirms that the desktop calendar resizes from 430 px to 360 px while the map expands; its flex basis follows the user-selected width. Evidence: `sync-calendar-resize.json`.

# Analysis performance verification — 30 October 2026

The production backend, worker and frontend were rebuilt and recreated without deleting database/cache volumes. Source publications were preserved. Targets below are distinguished from measured results and remaining verification limits.

## 1. Diagnosis and responsible functions

`run_pipeline.report()` held 5% before completed source units existed. The real work at that point was CMR discovery, `build_plan()` cache/integrity checks and upfront `AppEEARS.prepare()` yearly-block creation. Later `AppEEARS.extract()` could wait on remote processing for up to 1800 seconds. The live snapshot had already advanced to subset download at 12%; we did not submit more tasks to reproduce a notification-producing historical 5% interval. Per-stage durations for that historical interval cannot be reconstructed from old telemetry.

The second cause was unnecessary work: frontend `start()` unconditionally sent retry=true, explicitly requeuing legitimate QA-partial publications. Preview was also required before Analyze. Existing status/SSE code repeatedly deserialized ~690 KB result JSON solely to check availability. Local replay additionally regenerated every map image and repeatedly scanned cache/result quotas; the derived-content cache removes that repeated work on hits.

See `FAST_ANALYSIS_DIAGNOSIS_BEFORE.md` for the pre-change observations and their limits.

## 2. NASA audit and policy

* Remote AfterFire tasks before: **27**. Local manifests: **25**. Full task IDs, names, dates, products, AOIs, timestamps, remote states and local output inventories are in `appeears-task-audit-full.json`.
* Exact duplicate complete requests: **0**; topologically identical AOI/request pairs: **0**, with no near-equal geometry candidates. Comparing dates/layers without AOIs would falsely group distinct requests.
* Remote tasks after the fix: **27**; new task IDs: **0**. No remote tasks were deleted/cancelled. `appeears-task-audit-after.json` records the comparison.
* Backend/worker Compose configuration confirms submission disabled. Guards execute before authentication and before task HTTP transport. Maintenance callers use the same guard.
* Existing outputs remain readable. One previously active job was checkpointed while stopping the worker, then resumed using its saved tasks. An initial bounded-HDF budget rejection exposed incomplete saved-manifest handling; the planner now selects `saved_subset` for such manifests and resumes them with zero submissions. The job ID was retained and ultimately published a real partial scientific result: 67 valid NDVI and 67 EVI observations. No burned cells could be uniquely associated, so its hotspot-buffer territory and insufficient-reference warnings remain explicit. The final attempt reused 53 sources and downloaded 66,389 bytes; prior attempts account for another 2,274,893 bytes. Elapsed 1102.89 s includes the original remote acquisition, restarts and verification activity and is not a fresh direct-provider duration.

The audit JSON includes local manifest links and 14 tasks with local job associations from publication provenance or last-progress records, but does not reconstruct every historical local job association for tasks never recorded locally. Historical local job provenance is retained in the database; no association is invented.

## 3. NASA compatibility

Direct NASA acquisition reuses the existing CMR / Earthdata HTTPS HDF provider, now selected by default for missing sources instead of submitting AppEEARS work. Both actual collection IDs and products were checked. Authenticated data requests returned HTTP 206 and the correct HDF4 signature: MOD13Q1 in 2.674 s, MCD64A1 in 2.868 s, reading four application bytes each. CMR metadata latency was 0.608 / 4.459 s in these samples. This signature probe is separate from the fresh full-array verification below.

Fresh exact August 2021 reference granules were subsequently downloaded through the actual `EarthdataDownloader.stream()` provider: **MOD13Q1 85,207,161 bytes in 79.817 s**, **MCD64A1 812,345 bytes in 4.025 s**. These loop durations include disk writes and quota checks, not just NASA network latency. Full HDF SHA-256 matches the retained originals; native grid, masks and all required layers match exactly at 376 vegetation cells and 94 burned-area cells. Validation/comparison took 1.389 / 0.233 s. Total scientific transfer was **86,019,506 application bytes**, peak RSS **177,616 KiB**, and private scratch-file peak about 86 MB. Both private downloads were removed after comparison. See `direct-nasa-fresh-equivalence.json`. This verifies fresh real direct-source equivalence without pretending a full multiyear job was benchmarked.

Harmony returned HTTP 200 capabilities for both collections but advertised **zero services and no subsetting capability**. The legacy Hyrax catalogs timed out. The current MOD13Q1 OPeNDAP granule link advertised by CMR returned authenticated **404** for DDS and DAS. No constraint-expression, native QA slicing or partial-array adapter was enabled without a successful scientific probe. No Harmony jobs were created. Direct full HDF is a bounded fallback where native partial access was not verified. See `DIRECT_NASA_ACQUISITION.md` and the capability JSON artifacts.

## 4. Reproducible benchmark scenarios

| Scenario | Measurement | Scope / limit |
|---|---|---|
| A: persisted scientific analysis | Status median **24.57 ms**; result median **297.24 ms**, max **1385.31 ms** | Ten warm localhost requests each; includes HTTP, excludes browser rendering |
| A: browser | Desktop first saved content **2.37 s**, Analyze **2.10 s**; mobile **2.11 s** / **1.68 s** | Real browser, no mocked API; first page load and clicking an already displayed saved result are distinct |
| B: sources/checkpoints/derived maps cached | **4.097 s**, **168** reused sources, **330** reused raster pairs, **0 network bytes** | Real-source offline replay; catalog frozen to saved real identities; no database publication. Does not measure a new complete API-to-publication job |
| C: partial cache / saved remote outputs | Browser immediately displays operation/worker status; existing job resumed and published a real partial result with **0 new tasks** | 67 NDVI + 67 EVI observations; 1102.89 s includes original task acquisition and restarts, not a new-job benchmark |
| D: all inputs absent | Two exact real HDFs freshly acquired, 86,019,506 bytes total; native arrays exact | 79.817 s MOD13Q1 + 4.025 s MCD64A1 transfer/write/quota time, peak RSS 177,616 KiB. Full multiyear job duration remains unmeasured |
| E: repeated Analyze | Eight simultaneous POSTs returned **one existing job**, unchanged attempts=4; median **451.95 ms**, max **562.97 ms** | Exact saved configuration, retry=false; no preflight or remote downloads |

Before-change single warm API samples were 37.082 ms status and 200.141 ms result. The final result median is not faster than that single baseline sample; the important fix is skipping the scientific job entirely. A prior saved cache-only attempt took 88.61 s. A later instrumented pre-derived-cache offline replay took 174.46 s with concurrent cache activity; these are not controlled A/B speedup measurements against the 4.097 s warm derived-cache replay.

The warm replay integrity counters read **1,192,286 bytes**, with **0.090 s** of hashing, instead of hashing the logical multi-gigabyte source volume. Logical cache bytes are not physical bytes read.

Reproduce:

```sh
# From project root, with the running app and its existing reference publication:
backend/.venv/bin/python scripts/benchmark_fast_analysis.py
node scripts/verify_fast_analysis_browser.mjs

# Isolated supported Python/HDF runtime; never points test fixtures at archive DB:
docker run --rm --network none -v "$PWD/backend/app:/app/app:ro" -v "$PWD/scripts:/scripts:ro" afterfire-backend pytest app/tests/ -q --disable-warnings
# PostgreSQL: use a separately created afterfire_test_* database and AF_TEST_DATABASE_URL.
```

`benchmark_cached_processing.py` runs inside the backend runtime with its actual cache/database mounted, without publishing; `BENCHMARK_LABEL` separates output folders and `BENCHMARK_OUTPUT` selects the evidence destination. Its catalog consists of the exact saved NASA identities and it rejects any scientific provider network attempt. It compares every observation scientific field, metrics and serialized burned geometry. It does create private benchmark asset hard links in a separate result folder.

## 5. Worker, cache, database and frontend changes

* Existing primary-key identities, concurrent-insert conflict handling, conditional retry and fenced leases remain authoritative. New jobs bind linked FIRMS footprint/dates; valid legacy publications preserve their identity and contents.
* Status/SSE select only publication IDs. The existing event result index gives 0.072 ms SQL execution in EXPLAIN ANALYZE; no unnecessary index migration was introduced.
* Source integrity generations, strict HDF validation and processed vegetation checkpoints remain. Derived TIFF/PNG reuse includes native floats, transform, renderer version, checksums and corruption detection. Legacy asset bootstrap compares native arrays and preview pixels before reuse. No scientific arrays are interpolated.
* Worker transitions log safe job/operation IDs, start/end timestamps, monotonic durations and counters. Planning/integrity metrics are exposed in telemetry. Heartbeat age is separate from last real operation activity. Repeated remote status replies update external-contact time without pretending unchanged task state is scientific progress.
* Configurable defaults: missing heartbeat 60 s, no progress 180 s, direct operation duration 600 s, with socket timeouts as well. Existing task polling is bounded by the configured operation duration and AppEEARS wait duration. Expired leases resume the existing job; saved sources and publications survive failure/retry.
* Native raster calls run in protected IO threads; no unsafe hard-kill of a running GDAL thread is added. A permanently hung native extension still requires process recovery; heartbeat is not presented as proof of data progress.
* Analyze no longer requires Preview and does not implicitly retry partial results. Explicit update/retry actions remain. FIRMS overview, cached science, current phase, worker health, last activity and last received status are distinguished. Finished job telemetry is collapsed under saved-job details so cached science is visible sooner; heartbeat health is displayed only for active work. React query/SSE cleanup and lazy Reburn code splitting remain; satellite basemaps remain.

## 6. Scientific and functional verification

* **149 SQLite tests passed; 149 PostgreSQL/PostGIS tests passed**, in isolated databases under the supported Docker Python 3.12/HDF4 runtime. The host Python 3.15 environment lacks pyhdf/HDF4 development headers; its two HDF-dependent failures were environment failures, not counted as passes. Tests cover phases 1–6, API, persistence, source integrity, strict QA, recovery assessments, comparison, Reburn and gaps.
* Frontend TypeScript/Vite build passed. Desktop/mobile saved-analysis browser checks passed, including refresh, satellite tile loading, unchanged job/attempts and zero analysis POSTs on navigation. Live existing-task mobile status shows real operation activity without an automatic analysis POST.
* Additional real Phase 5 desktop/mobile browser verification passed Recovery Intelligence (471 displayed cells), linked NDVI/EVI dates, persisted recovery comparison, reload, GeoTIFF links and satellite tiles. Phase 6 browser verification passed 94 Reburn cells, layer changes, EVI/date synchronization, persisted reload and explicit missing-coverage states. Both reported zero browser errors; mobile width remained 390 px. See `fast-analysis-phase5-ui-verification.json` and `fast-analysis-phase6-browser-verification.json`.
* **Two freshly downloaded HDFs** are byte-identical to their exact retained NASA originals and match all required native arrays and masks, with zero task submissions.
* **20** real retained native HDF/subset comparisons cover both products, exact integer/QA arrays and native cell coordinates. The equivalence verifier now excludes unrelated AOIs and uses temporary descriptors with a read-only source-cache mount.
* The FIRMS archive count remains 803,761 detections (802,234 Italy), matching prior Phase 6 evidence. Reference publication after container recreation has exactly the original SHA-256: `4c8c61e3c1a1227882fd6197ba0e54b537b6116123394b6ed251a8352d35597f`. It still has **154 valid NDVI**, **154 EVI**, **94 burned cells**, **20.1779152898568 km²**. Offline replay reproduces all scientific observations, metrics and cells.
* Dedicated policy tests verify blocked POST task variants before any network, restart without a manifest, default direct planning, saved incomplete task reuse, no fallback on direct-provider outage, independent heartbeat/stall reporting and corrupt derived-raster rebuilding. Legacy submission adapter tests explicitly opt in against mocked transport only.

## 7. Changed files and evidence

Backend: `core/config.py`, `providers/appeears.py`, `providers/modis_catalog.py`, `api/routes/event_analysis.py`, `services/analysis_jobs.py`, `acquisition_plan.py`, `planning_jobs.py`, `post_fire_pipeline.py`, `reburn_jobs.py`, `analysis_progress.py`, `satellite_rasters.py`; policy tests in `test_fast_analysis.py`, adapter opt-in updates in `test_phase4_acquisition.py`.

Frontend: `EventAnalysisPage.tsx`, `AnalysisProgressPanel.tsx`, `types/satellite.ts`. Configuration: `.env.example`, `compose.yaml`. Scripts: API/browser/cache benchmarks, authenticated access verifier and safe native equivalence verifier. Required README/pipeline/cache/preflight/science/performance docs were updated; new fast-analysis, NASA acquisition, policy and verification docs were added.

Evidence JSON/PNG files named `fast-analysis-*`, `direct-nasa-*`, `opendap-array-probe.json`, `harmony-collection-capabilities.json` and `appeears-task-audit-*` contain raw measurements. Existing scientific database rows, original NASA sources, historical evidence and satellite basemaps were preserved.

## 8. Remaining limits

A working MOD13Q1/MCD64A1 partial-array OPeNDAP endpoint was not demonstrated; direct HDF remains the controlled fallback. Fresh two-granule direct acquisition equivalence is verified; a complete new multiyear direct-acquisition job and its complete resource profile remain unbenchmarked. Final first-content browser samples are 2.11–2.37 s and the desktop Analyze sample is 2.10 s, slightly above the ideal 1–2 s. The warm result API meets the sub-500 ms ideal in these samples; no universal latency guarantee is claimed. A cache-only full database publication duration was not separately benchmarked. Repeating Analyze after the newly resumed job published returned its existing partial result in 54.3 ms with unchanged job/attempts. Historical 5% stage-by-stage timings cannot be recovered retroactively. Existing remote-task emails may still arrive. No account notification setting was changed.

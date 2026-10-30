# Satellite Recovery Story (Phase 4)

The existing event analysis page is the sole entry point. Start from the Explorer,
open a real FIRMS candidate and preview the acquisition plan. Configure pre/post
years, the explicit observation cutoff, provisional buffer and acquisition
strategy. `auto` always prefers verified cached data. A parameter change
invalidates the displayed preflight; a new preview is required before starting.
Preview does not enqueue a job or submit a NASA task.

## Scientific timeline

The timeline contains the expected MOD13Q1 composite dates (including explicit
quality/missing/incomplete states), plus associated FIRMS dates. Slider, date and
year selectors, previous/next buttons and chart clicks share `selectedDate`.
Native range controls support keyboard and touch. Event start/end are labelled;
selected composites display their start and end, phase, product and resolution.
NDVI, EVI, coverage, anomaly, baseline and time from last FIRMS detection are
reported for the selected date. Missing values stay null, never zero.

The map uses the shared `SatelliteBasemap` with Esri World Imagery. This is
geographic context with varying/unknown acquisition dates, not a historical
photograph. NDVI/EVI are dated, QA-masked false-colour scientific rasters with a
fixed −0.2…1 scale. Nodata is transparent. Native scaled GeoTIFFs can be downloaded.
Map previews alone are projected with nearest-neighbour for display; scientific
statistics and stored GeoTIFFs remain on the native sinusoidal grid.

## Comparison

A/B selectors choose distinct valid pre/post composites. The two rasters share
**one Leaflet map**, hence exactly the same centre, zoom, CRS and AOI. Both panes
are clipped on complementary sides at a keyboard/touch slider position, so nodata never reveals the other date. Clipping is recomputed on pan,
zoom and resize and never changes geographic coordinates. Both dates, medians
and valid fractions are labelled. The reported B−A is a difference of spatial
medians, not a pixelwise difference on potentially different QA masks.

No pixelwise change map is produced. It would require a separately validated
common-cell mask. An increase in an index is not evidence of complete ecosystem
recovery. Seasonal and cloud-coverage differences remain explicit.

## Playback and chart

Play/Pause traverses only composites with a valid statistic and a map asset.
Slow/normal/fast delays are 4/2/0.8 seconds. A frame must load before the next
advance; raster errors stop advancement. Changing index/event/result or hiding
the tab pauses playback. At the end it stops; pressing Play again starts at the
first available observation. At most the next composite's images are prefetched.
There are no interpolated satellite frames.

The existing Recharts component shows observed values, seasonal median and
reference envelope, the selected time and fire interval, and anomaly on a
separate right-hand axis. Clicking a date updates the shared selection.

## API and persistence

- `POST /api/v1/events/{event_id}/analysis/preflight`: validated configuration;
  catalog discovery, verified cache, resource limits, provider groups and an
  honest nullable network estimate. No analysis/task is created.
- Existing `POST .../analysis`, `GET .../analysis/status`, `GET .../analysis/stream`,
  `GET .../analysis/result`, `GET .../vegetation/timeseries` and asset endpoints
  retain their contracts. Result payloads additionally contain `acquisition_plan`.
- SSE reuses `event_analysis_progress`; task IDs, remote phases and temporal-block
  counters extend the same durable telemetry. No rate is shown while NASA is
  processing. Only atomic database publication sets overall progress to 100%.
- Source/task/derived-window manifests persist on the shared filesystem; final
  scientific rows and result metadata persist in the existing database.

See [subsetting](SATELLITE_SUBSETTING.md), [verification](PHASE4_VERIFICATION.md)
and the replay helpers `scripts/verify_phase4_equivalence.py` and
`scripts/verify_phase4_ui.mjs`.


## Integrazione Fase 5 — Recovery Intelligence

La Fase 5 estende questa implementazione preservandone osservazioni e risultati. Il preflight ora restituisce 202 con una pianificazione persistente, non un piano sincrono. Si vedano [architettura/API](RECOVERY_INTELLIGENCE.md), [metodologia degli indicatori](RECOVERY_ASSESSMENT_METHODOLOGY.md), [analisi per pixel](SPATIAL_RECOVERY_ANALYSIS.md), [preflight asincrono](ASYNC_PREFLIGHT.md), [gestione cache](CACHE_MANAGEMENT.md) e [verifica Fase 5](PHASE5_VERIFICATION.md). Le descrizioni delle prove Fase 3/4 restano evidenze storiche, non misurazioni della nuova implementazione.


## Phase 6 — Reburn & Recovery Gap

The existing implementation is extended by [Reburn Intelligence](REBURN_INTELLIGENCE.md), [observed episode methodology](REBURN_DETECTION_METHODOLOGY.md), [shared-area Recovery Gap](RECOVERY_GAP.md) and [cumulative vegetation](CUMULATIVE_VEGETATION.md). See [measured infrastructure changes](PERFORMANCE_OPTIMIZATION.md) and [verification and limitations](PHASE6_VERIFICATION.md). Previous-phase publications and reports are preserved.


## API-first acquisition update (2026-10-30)

Normal Analyze now prefers persisted results and verified native sources/subsets, then configured compatible Collection 6.1 APIs. Missing data never triggers automatic full-tile HDF transfer or new AppEEARS submission. Scientific QA, baselines, anomalies, recovery and reburn calculations are unchanged. ORNL collection equivalence and live Earth Engine access remain explicit limitations. See [API-first engine](API_FIRST_SATELLITE_ENGINE.md), [provider equivalence](PROVIDER_EQUIVALENCE.md) and [verification](API_FIRST_VERIFICATION.md) for current behavior; older acquisition descriptions above are historical.

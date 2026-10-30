# AfterFire — The Life of a Forest After Fire
*Understand the fire. Follow the recovery. Discover what happens next.*

[![NASA Space Apps 2026](https://img.shields.io/badge/NASA%20Space%20Apps-2026%20Challenge-orange.svg)](https://www.spaceappschallenge.org/2026/challenges/harmonization-of-modis-and-viirs-hot-spots/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI%20%2F%20Python-009688.svg)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/Frontend-React%2018%20%2F%20TypeScript-61dafb.svg)](https://react.dev/)
[![TailwindCSS](https://img.shields.io/badge/Style-Dark%20Cinematic%20Tailwind-38bdf8.svg)](https://tailwindcss.com/)
[![Tests](https://img.shields.io/badge/Tests-Pytest%20Passing%20(9%2F9)-brightgreen.svg)]()

An end-to-end scientific web application submitted for the **NASA Space Apps Challenge 2026**:
**Harmonization of MODIS and VIIRS Hot Spots** with post-fire ecological recovery extension.

---

## 1. Project Vision

AfterFire reconstructs the complete environmental story of a territory before, during, and after a wildfire.

Rather than being another static map of fire markers, AfterFire addresses concrete scientific questions:
- **Where and when was combustion activity detected?** Harmonizing NASA MODIS (1km) and VIIRS (375m) observations.
- **What physical surface was burned?** Differentiating active point thermal hotspots from MODIS MCD64A1 500m pixel-mapped burned areas.
- **What was the pre-fire baseline?** Calculating observed pre-fire mean vegetative reference values from MODIS MOD13Q1 250m 16-day composites.
- **How did canopy greenness evolve after the event?** Quantifying drop magnitude, trajectory recovery quotients, and QA masking.
- **Are there areas exhibiting delayed or truncated recovery?** Detecting recurring wildfires and compound disturbances before canopy restoration.
- **How reliable are these conclusions?** Enforcing strict traceability, zero hallucinated figures, explicit remote-sensing limitations, and transparent demo vs live tagging.

> **Disclaimer:** AfterFire is an independent community project developed for the NASA Space Apps Challenge 2026. It is not an official service or endorsement of NASA.

---

## 2. Architecture & Technology Stack

```
afterfire/
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI application & lifespan startup
│   │   ├── core/config.py              # Pydantic BaseSettings & environment
│   │   ├── db/database.py              # SQLAlchemy 2.0 async engine & session
│   │   ├── models/                     # SQLAlchemy models (Area, Fire, Burned, Veg, Event, Rec)
│   │   ├── schemas/                    # Pydantic validation & OpenAPI responses
│   │   ├── providers/                  # NASA FIRMS, MCD64A1, MOD13Q1, GIBS adapters
│   │   ├── analysis/                   # Harmonization, Recovery & Recurrence Engines, AI Analyst
│   │   ├── jobs/seed_data.py           # Calibrated historical presets & initial data
│   │   └── tests/                      # Automated test suite (Pytest & AsyncClient)
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/                 # Map, Timeline, Recovery & Calendar charts, Layout
│   │   ├── pages/                      # Home, Explorer, Territory, Recovery, Recurrence, Compare, Report
│   │   ├── api/client.ts               # Axios REST API client
│   │   └── styles/index.css            # Dark cinematic Tailwind & Leaflet styles
│   ├── Dockerfile                      # Multi-stage build + Nginx alpine
│   ├── vite.config.ts
│   └── package.json
├── compose.yaml                        # Docker Compose deployment (PostGIS, Backend, Frontend)
├── scripts/                            # dev.sh, test.sh
├── .env.example
└── README.md
```

### Backend
- **Python 3.12+** / **FastAPI**: Asynchronous REST API with automatic OpenAPI documentation (`/docs`).
- **SQLAlchemy 2.0 (Async)**: Dual support for SQLite (`sqlite+aiosqlite`) for zero-setup local execution and PostgreSQL/PostGIS.
- **NumPy, Pandas, SciPy, Shapely**: Remote-sensing numerical calculations and spatiotemporal clustering.
- **HTTPX**: Non-blocking client for NASA FIRMS Area API and external feeds.
- **Pytest & Pytest-Asyncio**: Comprehensive automated validation suite.

### Frontend
- **React 18 & TypeScript (Vite)**: Component-driven architecture.
- **Tailwind CSS**: Dark cinematic palette with emerald, fire-red, amber, and slate accents.
- **React Leaflet & Leaflet**: High-performance interactive cartography with NASA GIBS true color context.
- **Recharts**: Scientific time-series charts with confidence bands and dual-axis calendars.
- **TanStack React Query**: Efficient client-side caching, stale-time handling, and loading states.
- **Lucide React**: Vector scientific icons.

---

## 3. NASA Challenge Requirements & Scientific Engines

### 3.1 Harmonization of MODIS and VIIRS Hot Spots (Challenge Core)
MODIS (1km nominal nadir) and VIIRS (375m I-band) differ fundamentally in pixel footprint and radiant sensitivity:
- VIIRS detects fires up to 3x–5x more frequently than MODIS over the exact same flaming perimeter.
- AfterFire **preserves full sensor provenance**: instrument, satellite, acquisition time, raw confidence, and Fire Radiative Power (MW).
- Standardizes confidence into normalized tiers: `high`, `nominal`, `low`.
- Groups observations into multi-sensor activity calendars without double-counting physical fire perimeters.
- Implements greedy spatiotemporal proximity grouping (7km / 3-day max temporal gap) to infer candidate disturbance events.

### 3.2 Pre-Fire Baseline & Recovery Trajectory Engine
- **Multi-Year Seasonal Baseline**: Uses 16-day MODIS MOD13Q1 NDVI composite observations prior to the fire disturbance to calculate baseline mean ($\mu$) and standard deviation ($\sigma$).
- **Disturbance Trough**: Identifies post-fire minimum composite value and computes disturbance drop magnitude and percentage.
- **Recovery Quotient**:
  $$\text{Recovery \%} = \frac{\text{NDVI}_{\text{latest}} - \text{NDVI}_{\text{trough}}}{\text{NDVI}_{\text{baseline}} - \text{NDVI}_{\text{trough}}} \times 100$$
- **Qualitative Status Classification**:
  - `Substantially Recovered` ($\ge 90\%$)
  - `Partial Recovery` ($60\% - 89\%$)
  - `Stagnant / Slow Recovery` ($< 60\%$)
- **QA Bitmask Filtering**: Uses 16-bit MOD13Q1 QA words to exclude cloud, snow/ice, and heavy aerosol contamination.
- **Explicit Limitations**: Documents that spectral greenness reflects chlorophyll absorption, not climax biodiversity, soil carbon, or age structure.

### 3.3 Multiple Wildfire Recurrence & Interrupted Regrowth
- Tracks return intervals between consecutive events on the same territory.
- Detects compound disturbances where a subsequent fire occurs before vegetation returns to pre-fire baseline.

### 3.4 AI Analyst: Deterministic & Fact-Grounded LLM
- **Default Mode**: 100% deterministic scientific explainer generating verified narrative syntheses directly from computed metrics.
- **Optional Mode**: Fact-grounded LLM (OpenAI GPT-4o-mini) when `LLM_API_KEY` is provided, strictly constrained to cite only computed metrics and never hallucinate numbers.

---

## 4. Quick Start & Execution

### Option A: Local Development (Fastest, zero-setup)

#### 1. Prerequisites
- Python 3.10+
- Node.js 18+ and npm

#### 2. Backend Setup
```bash
cd afterfire/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
The backend initializes the database and seeds calibrated synthetic study cases only when
`DEMO_MODE=true`. Real-data mode is the default; create a study area and configure a NASA
FIRMS MAP key to retrieve observations. The Explorer hides synthetic presets and only
displays real observations, grouped into zoom-dependent map clusters.

The Explorer opens on Italy and defaults to all available dates in the local archive.
For complete Italy ingestion, resumable annual downloads, API backfill and indexing, see [backend/README.md](backend/README.md).
The map remains globally navigable; its Italian starting view is not a geographic
restriction on map movement or area searches. An optional WGS84 circle can be drawn
anywhere on the map and searches only observations inside its radius, with the
selected date and sensor filters. Outside the imported coverage, the Explorer reports
that local data are unavailable rather than implying that no fires occurred.
Synthetic detections are excluded from real-data results by default. Zoom-dependent
map clusters are visual aggregations, not individual fires; the results list shows
algorithmic event candidates separately and can highlight one on the map. Candidates and detection memberships are indexed outside map requests and paginated on the server.
`GET /api/v1/events/{event_id}` supports direct, shareable event-analysis URLs at
`/events/{event_id}`. These candidates are not official fire perimeters. Display clusters aggregate the full matching observation set in SQL; candidate pages refer to complete persisted histories. The Explorer
search URL is preserved when navigating to and back from a candidate analysis.
Open API documentation at: **http://localhost:8000/docs**

#### Geographic analysis limits

The backend validates the analysis configuration at startup. Set the WGS84 bounding
box as `west,south,east,north` in `.env`; the example values are editable defaults,
not a permanent analysis period. `MAX_DOWNLOAD_DAYS_PER_REQUEST`,
`MAX_CONCURRENT_DOWNLOADS`, and `MAX_DOWNLOAD_SIZE_MB` bound active-fire retrieval.
FIRMS responses are requested for the bounding box at NASA rather than fetched
globally and filtered afterward.

The Explorer's optional **Draw circle** search is independent of the configured
analysis bounding box used for provider downloads. Users can pan and zoom globally,
draw or clear a circular area, and return to the Italy view without changing their
date or sensor filters. A circle search is evaluated against the local archive only;
it does not trigger a global download. The separate analysis workflow continues to
use the configured bounding box and date interval to constrain provider retrieval.

The current automated remote downloader supports NASA FIRMS active-fire feeds
(MODIS and VIIRS Suomi-NPP, NOAA-20 and NOAA-21; standard and NRT feeds). MCD64A1 and MOD13Q1 are currently parsed/imported
products; AfterFire does not claim to automatically retrieve them or apply source
side region/date filtering to their global granules. FIRMS NRT availability is
provider-controlled, so a valid historical date range may still be rejected by
NASA; the API reports provider failures instead of silently substituting data.
See the [NASA FIRMS API documentation](https://firms.modaps.eosdis.nasa.gov/api/)
for its MAP_KEY requirement and transaction limits.

Downloaded FIRMS CSV responses are cached under `~/.cache/afterfire` for local
development. Docker Compose stores them in the persistent `afterfire-cache`
volume. Cache inspection and disposable-cache removal are available at
`GET /api/v1/analysis/cache` and `DELETE /api/v1/analysis/cache`; these operate
only on cached provider CSV files and never touch the application database.

#### 3. Frontend Setup
```bash
cd afterfire/frontend
npm install
npm run dev
```
Open web application at: **http://localhost:3000** (or http://localhost:5173).

---

### Option B: Docker Compose

```bash
cd afterfire
cp .env.example .env
docker compose up --build
```
Services started:
- `frontend`: **http://localhost:3000**
- `backend`: **http://localhost:8000**
- `db`: PostgreSQL / PostGIS 15 on port `5432`

---

## 5. Running Verification & Automated Tests

A dedicated test and build verification script is included:

```bash
./afterfire/scripts/test.sh
```

Or execute tests manually:
```bash
# Backend Pytest Suite
cd afterfire/backend
PYTHONPATH=. .venv/bin/pytest app/tests/ -v

# Frontend TypeScript & Vite Build
cd afterfire/frontend
npm run build
```

---

## 6. Hackathon Demo Walkthrough (For Judges)

1. **Homepage (`/`)**:
   - Review project vision and the 3 core phases: *Before*, *Fire*, *Recovery*.
   - Notice the persistent calibrated demo data banner and links to official NASA data sources.
   - Click **Explore the Map**.

2. **Interactive Explorer (`/explorer`)**:
   - Start with the map centered on Italy and its currently available archive data.
   - Use date and sensor filters to update the visible clusters and synchronized
     results list; the active period and archive coverage remain explicit.
   - Pan anywhere in the world and optionally draw a circle to search that area.
     Clear it to return to the Italian results, or use **Return to Italy** to restore
     the initial view while retaining the filters.
   - Treat visual clusters as groups of observations, not confirmed individual fires.
     Local coverage gaps are reported as unavailable data, not as evidence of no fire.
   - Synthetic study cases remain explicitly identified as **DEMO DATA** and separate
     from real satellite observations.

3. **Territory Story & Synchronized Timeline (`/territory/rhodes-greece-2023`)**:
   - Scrub through the 4 phases:
     - *1. Before Fire*: Baseline canopy greenness.
     - *2. Fire Period*: Active thermal detections and flaming frontiers.
     - *3. Immediate Post-Fire*: MCD64A1 burned scar and initial NDVI crash.
     - *4. Recovery Trajectory*: Regrowth monitoring.
   - Press **Play Timeline** to watch the map automatically synchronize its layers.

4. **Recovery Explorer (`/recovery/rhodes-greece-2023`)**:
   - Inspect the interactive Recharts trajectory:
     - Pre-fire baseline (blue dashed line) with $\pm 1\sigma$ variance band.
     - Fire disturbance line in red.
     - 16-day observed composite NDVI (green line).
   - Review scorecard: Pre-fire baseline (`0.650`), Trough (`0.170`, `-73.8%`), Latest observed (`0.410`), Recovery status (`Partial Recovery, 64%`).
   - Interact with the **Scientific AI Analyst**: Switch tabs between *Overview*, *Recovery*, *Harmonization*, and *Recurrence*.

5. **Recurring Wildfires & Compound Disturbance (`/recurrence/kangaroo-island-2020`)**:
   - Explore the Black Summer multi-fire case.
   - Notice the compound disturbance alert: Event 2 occurred before vegetation had restored to baseline, demonstrating recovery truncation.

6. **Cross-Territory Comparison (`/compare`)**:
   - Compare *Rhodes Island* vs *Jasper National Park*.
   - Note the automatic **Scientific Comparability Advisory**: Flags distinct biomes (Mediterranean pine vs Boreal coniferous) and contrasting resprouting adaptations.

7. **Exportable Scientific Report (`/report/rhodes-greece-2023`)**:
   - View complete printable synthesis with bounding box, dataset citations, trajectory chart, and limitations.
   - Click **Print Report / Save PDF** for an instant high-resolution summary.

8. **Datasets & Provenance (`/datasets`)**:
   - Inspect status of all NASA feeds and configuration instructions for `FIRMS_MAP_KEY`.
   - Ingest custom user-downloaded FIRMS CSV files through the upload tool.

---

## 7. Configuration & Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `DATABASE_URL` | SQLAlchemy async connection string | `sqlite+aiosqlite:///./afterfire.db` |
| `FIRMS_MAP_KEY` | NASA ESDIS FIRMS MAP KEY for live queries | *(Optional)* |
| `EARTHDATA_USERNAME` | NASA Earthdata login username | *(Optional)* |
| `EARTHDATA_PASSWORD` | NASA Earthdata login password | *(Optional)* |
| `LLM_API_KEY` | OpenAI API key for AI Analyst narrative | *(Optional)* |
| `DEMO_MODE` | Seeds and enables synthetic study cases | `false` |
| `ANALYSIS_BBOX` | Default region as west,south,east,north WGS84 coordinates | `14.7,37.1,15.4,37.8` |
| `ANALYSIS_REGION_NAME` | Human-readable configured region label | `Sicily East` |
| `ANALYSIS_START_DATE` / `ANALYSIS_END_DATE` | Initial analysis date interval | `2024-01-01` / `2026-10-27` |
| `MAX_DOWNLOAD_DAYS_PER_REQUEST` | Maximum days in one FIRMS API window (1–5) | `5` |
| `MAX_CONCURRENT_DOWNLOADS` | Maximum simultaneous provider downloads | `2` |
| `MAX_DOWNLOAD_SIZE_MB` | Maximum bytes accepted per provider operation/upload | `250` |
| `DATA_CACHE_ENABLED` | Reuse downloaded provider responses | `true` |
| `ALLOW_GLOBAL_DOWNLOADS` | Explicit opt-in for whole-globe requests | `false` |

---

## 8. NASA Data Sources & Citations

- **NASA FIRMS Active Fire (MODIS C6.1)**: Giglio, L., et al. (2016). *The collection 6 MODIS active fire detection algorithm*. Remote Sensing of Environment, 178, 31-41.
- **NASA FIRMS Active Fire (VIIRS 375m)**: Schroeder, W., et al. (2014). *The New VIIRS 375 m active fire detection product*. Remote Sensing of Environment, 143, 85-96.
- **MODIS MCD64A1 Burned Area (500m)**: Giglio, L., et al. (2018). *The Collection 6 MODIS burned area mapping algorithm and product*. Remote Sensing of Environment, 217, 72-85.
- **MODIS MOD13Q1 Vegetation Indices (250m)**: Didan, K. (2015). *MOD13Q1 MODIS/Terra Vegetation Indices 16-Day L3 Global 250m SIN Grid V006*. NASA LP DAAC.
- **NASA GIBS / Worldview**: NASA Earth Science Data and Information System (ESDIS).

---

## 9. License

This project is licensed under the MIT License — see the LICENSE file for details. Built for the NASA Space Apps Challenge 2026.

## On-demand post-fire analysis

The event page now supports a persistent NASA MODIS analysis worker, event-specific burned cells, QA-screened NDVI/EVI, seasonal baselines, dated rasters and descriptive recurrence evidence. Start with [Post-Fire Recovery](docs/POST_FIRE_RECOVERY.md), [pipeline](docs/SATELLITE_DATA_PIPELINE.md), [methodology](docs/SCIENTIFIC_METHODOLOGY.md), [cache configuration](docs/ANALYSIS_CACHE.md) and [verification evidence](docs/POST_FIRE_VERIFICATION.md). Real acquisition requires working backend Earthdata credentials; the checked-in verification report states what was actually acquired.

## Phase 4 — Recovery Story

Event analysis now previews cache-aware acquisition, requests annual NASA AppEEARS native spatial subsets with all required QA layers, and retains the original bounded HDF provider. Recovery Story adds real-composite playback, year/date selection, a shared-map Before/After divider and synchronized anomaly charts. The 5 GiB job limit applies to new network bytes; cache, block, temporary and derived-result limits are separate. See [Recovery Story](docs/RECOVERY_STORY.md), [subsetting](docs/SATELLITE_SUBSETTING.md) and [verification evidence](docs/PHASE4_VERIFICATION.md).


## Fase 5 — Recovery Intelligence

La pagina evento include assessment stagionale NDVI/EVI, persistenza osservata, baseline per pixel, mappa delle anomalie e GeoTIFF multibanda. Compare Recovery confronta eventi reali per mesi dall’incendio, con controlli di qualità. Preflight persistente asincrono, cache metadati TTL e cleanup conservativo con dry-run mantengono separati rete, catalogo e spazio locale.

- [Architettura e API](docs/RECOVERY_INTELLIGENCE.md)
- [Metodologia scientifica](docs/RECOVERY_ASSESSMENT_METHODOLOGY.md) e [analisi spaziale](docs/SPATIAL_RECOVERY_ANALYSIS.md)
- [Preflight asincrono](docs/ASYNC_PREFLIGHT.md) e [gestione cache](docs/CACHE_MANAGEMENT.md)
- [Risultati, test e limiti verificati](docs/PHASE5_VERIFICATION.md)

Il POST preflight restituisce ora 202 e un planning ID: i client devono leggere il piano da GET/SSE quando ready. Nessun download o task NASA viene avviato dalla pianificazione. Gli indicatori descrivono gli indici vegetativi osservati e non certificano recupero ecologico completo.


## Phase 6 — Reburn & Recovery Gap

The existing implementation is extended by [Reburn Intelligence](docs/REBURN_INTELLIGENCE.md), [observed episode methodology](docs/REBURN_DETECTION_METHODOLOGY.md), [shared-area Recovery Gap](docs/RECOVERY_GAP.md) and [cumulative vegetation](docs/CUMULATIVE_VEGETATION.md). See [measured infrastructure changes](docs/PERFORMANCE_OPTIMIZATION.md) and [verification and limitations](docs/PHASE6_VERIFICATION.md). Previous-phase publications and reports are preserved.


## Fast analysis update — 30 October 2026

Analysis now opens saved scientific publications without preflight or automatic retry. New AppEEARS task submission defaults to disabled; missing sources use bounded direct NASA HDF access. See [Fast analysis](docs/FAST_ANALYSIS.md) and [measured verification](docs/ANALYSIS_PERFORMANCE_VERIFICATION.md).


## Global Explorer and API-first analysis

The Explorer now provides a world map, satellite filters, UTC date controls, timeline, searchable/saved/shareable views, bounded hotspots/SQL clusters and event-scoped persisted burned-area/NDVI/EVI overlays. The initial view remains Italy. Local archive coverage and recent online FIRMS access are distinguished; contextual satellite basemaps are not historical imagery of the selected fire date.

Normal Analyze reuses scientific results and valid native caches, then compatible configured APIs. **Automatic full HDF downloads are disabled.** Earth Engine requires an externally registered project and runtime credentials; live ORNL Collection 6.1 equivalence is not verified and no substitution is made. No billing or NASA email orders are activated. The existing Recovery Story, Recovery Intelligence, comparison, reburn and gap flows remain available.

See [global explorer](docs/FIRMS_STYLE_EXPLORER.md), [layers and timeline](docs/MAP_LAYERS_AND_TIMELINE.md), [API-first engine](docs/API_FIRST_SATELLITE_ENGINE.md), [Earth Engine setup](docs/EARTH_ENGINE_PROVIDER.md), [verification](docs/API_FIRST_VERIFICATION.md) and [Git history security](docs/GITHUB_HISTORY_SECURITY.md). Install local credential checks with `git config core.hooksPath .githooks`.

Earth Engine activation requires an externally registered Google Cloud project.
Follow [live setup](docs/EARTH_ENGINE_LIVE_SETUP.md) for registration, minimal IAM,
private ADC authentication and the backend/worker secret overlay. Run
`python -m app.providers.earth_engine_check --live` in both server runtimes to
verify bounded real collection reads; `/api/v1/health` reports configuration
without claiming live access. [Current activation evidence](docs/EARTH_ENGINE_LIVE_VERIFICATION.md)
distinguishes verified software from the outstanding live scientific checks.

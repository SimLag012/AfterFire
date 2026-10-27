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
- **What was the pre-fire baseline?** Calculating seasonal multi-year vegetative reference values from MODIS MOD13Q1 250m 16-day composites.
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
- Implements spatiotemporal clustering (DBSCAN 7km / 3-day max temporal gap) to infer candidate disturbance events.

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
The backend initializes the database and seeds the calibrated study cases automatically.
Open API documentation at: **http://localhost:8000/docs**

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
   - Switch between calibrated territories (e.g. *Rhodes Island 2023*, *Jasper Canada 2024*, *Kangaroo Island 2020*).
   - Toggle layers:
     - **MODIS (1km)**: Yellow/red circles with white rims.
     - **VIIRS (375m)**: Blue/red circles with cyan rims (higher spatial density).
     - **MCD64A1 Burned Area**: 500m mapped burnt patches.
     - **GIBS True Color**: NASA Worldview RGB background layer.
   - Click any hotspot marker to inspect its acquisition timestamp, confidence tier, and Fire Radiative Power (MW).
   - Expand the **Harmonized Activity Calendar** at the bottom right.

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
| `DEMO_MODE` | Flags synthetic samples transparently | `true` |

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


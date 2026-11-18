<div align="center">

# 🔥 AfterFire

### The life of a forest after fire

*Explore the fire. Compare the observations. Follow the vegetation.*

[![Live demo](docs/images/link-demo.svg)](https://afterfire-public-demo.vercel.app)
[![Watch video](docs/images/link-video.svg)](https://drive.google.com/file/d/1BwVHhXkj6QrwVJ8ON-PGzbh3a-ASdFA5/view?usp=sharing)
[![Run locally](docs/images/link-local.svg)](#run-locally)
[![Scientific methods](docs/images/link-science.svg)](docs/SCIENTIFIC_METHODOLOGY.md)

![NASA Space Apps 2026](docs/images/badge-space-apps.svg)
![FastAPI · Python](docs/images/badge-fastapi.svg)
![React · TypeScript](docs/images/badge-react.svg)
[![License: MIT](docs/images/badge-license.svg)](LICENSE)

</div>

AfterFire connects NASA MODIS and VIIRS fire observations with dated satellite evidence of vegetation change. Follow an event from thermal detections to burned cells, seasonal NDVI/EVI trajectories and evidence of repeated burning on the same ground.

Built by **Ash Happens** for the **NASA Space Apps Challenge 2026**, addressing **Harmonization of MODIS and VIIRS Hot Spots**. The project brings historical fire activity and post-fire vegetation evidence into one workflow for researchers, environmental organizations and land managers.

## See it in action

[![Recorded AfterFire walkthrough: Explorer, Before/After, vegetation timeline and native-cell recovery](docs/media/afterfire-demo.gif)](https://drive.google.com/file/d/1BwVHhXkj6QrwVJ8ON-PGzbh3a-ASdFA5/view?usp=sharing)

**[Watch the project demonstration](https://drive.google.com/file/d/1BwVHhXkj6QrwVJ8ON-PGzbh3a-ASdFA5/view?usp=sharing)** — the video shared with the NASA Space Apps project submission. The animated preview above is a separate short walkthrough of the application using published scientific data. The [public demo](https://afterfire-public-demo.vercel.app) serves a limited, read-only snapshot; new acquisitions and analyses run in the full local application.

## From fire observations to recovery evidence

```mermaid
flowchart LR
    A["MODIS + VIIRS<br/>Thermal observations"] --> B["Explorer<br/>Candidate event"]
    B --> C["MCD64A1<br/>Observed burned cells"]
    B --> D["MOD13Q1<br/>Dated NDVI / EVI"]
    C --> E["Recovery Story<br/>Before / After + timeline"]
    D --> E
    E --> F["Recovery Intelligence<br/>Seasonal and native-cell evidence"]
    C --> G["Reburn + Recovery Gap<br/>Repeated burning on shared cells"]
    D --> G
    style A fill:#251e17,stroke:#f69c63,color:#fff4e6
    style E fill:#1b2b25,stroke:#85b6a4,color:#effbf5
    style F fill:#1b2b25,stroke:#85b6a4,color:#effbf5
```

### One territory, several kinds of evidence

![Before/After view of real MODIS composites for the July 2023 Ródos candidate](docs/images/recovery-story.webp)

**Recovery Story** pairs dated composites on a shared map, with a movable divider, observation playback and NDVI/EVI charts. Seasonal references give context to the observed changes; missing and QA-rejected observations remain gaps.

| Explore the observations | Inspect recovery on the ground |
| --- | --- |
| [![Explorer with archived MODIS/VIIRS observations and a hotspot calendar](docs/images/explorer.webp)](docs/images/explorer.webp) | [![Recovery Intelligence with seasonal reference classes on native MODIS cells](docs/images/recovery-intelligence.webp)](docs/images/recovery-intelligence.webp) |
| Filter dates and sensors, inspect original records and follow candidate events. Historical calendars distinguish acquired coverage from missing periods. | Inspect individual cells, seasonal anomalies, descriptive trends and persistent negative evidence. Reburn follows repeated mapped burns on the same native cells. |

Hotspots, candidate events and mapped burned cells have different meanings. Candidates are algorithmic groups, not official fire perimeters. Vegetation greenness does not establish complete ecological restoration, and missing observations do not establish absence of fire. Scientific overlays are dated measurements; the imagery beneath them is geographic context with independent dates. See the [methodology](docs/SCIENTIFIC_METHODOLOGY.md).

## Data behind the story

| Source | Role in AfterFire |
| --- | --- |
| NASA FIRMS · MODIS / VIIRS | Thermal observations with original sensor, acquisition time, confidence and FRP |
| MODIS MCD64A1.061 | Mapped burned cells, burn dates and uncertainty at nominal 500 m resolution |
| MODIS MOD13Q1.061 | NDVI/EVI at nominal 250 m resolution in 16-day composites |
| NASA HLS v002 / ESA Sentinel-2 | High-resolution optical evidence where supported and available |
| NASA GIBS / Worldview | Dated imagery for geographic context |
| NASA CMR / AppEEARS · Google Earth Engine | Product discovery and configured, bounded data access |

Geographic references also use GeoNames and OpenStreetMap-based services. Sources and acquisition paths retain their own coverage, access requirements and attribution. See [scientific methods](docs/SCIENTIFIC_METHODOLOGY.md) and [provider setup](docs/OPERATIONS.md).

## Run locally

Run these commands from the directory containing this README and `compose.yaml`. From the parent NASA workspace, first run `cd afterfire`.

### Docker Compose

Requires Docker Engine and Compose. For the first installation:

```bash
cp .env.example .env
# Configure the providers you intend to use in .env.
docker compose up --build
```

Open the **[web application](http://localhost:3000)** or **[API documentation](http://localhost:8000/docs)**. Compose starts PostgreSQL/PostGIS, FastAPI, the analysis worker and the frontend. Database and cache volumes persist between restarts. A fresh installation needs imported or acquired observations; the screenshots are existing publications, not seed data.

### Without Docker

Requires Python 3.12, Node.js 22, npm and the backend's native raster/HDF libraries. Docker includes the packaged scientific runtime if these libraries are unavailable on your host.

```bash
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
npm --prefix frontend ci
cp .env.example .env
backend/.venv/bin/python scripts/local.py
```

The launcher starts API, worker and Vite with local SQLite at `backend/afterfire.db`. Logs and the scientific cache are in `.local-runtime/`; Ctrl+C stops all three processes. This database is separate from Docker's PostgreSQL volume. On Windows, use `backend/.venv-windows/Scripts/python.exe` with a virtual environment created by `py -3.12 -m venv backend/.venv-windows`.

FIRMS acquisition needs `FIRMS_MAP_KEY`. Earth Engine needs an externally registered project and credentials available to both API and worker. Configuration alone does not verify access. See [.env.example](.env.example) and [provider setup and archive import](docs/OPERATIONS.md).

## How it fits together

```mermaid
flowchart TB
    UI["React + TypeScript<br/>Leaflet maps / Recharts"] --> API["FastAPI"]
    API --> DB[("SQLite or PostgreSQL / PostGIS")]
    W["Persistent analysis worker"] --> DB
    W --> P["Configured NASA / Earth Engine providers"]
    W --> CACHE[("Native sources + published assets")]
    API --> CACHE
    EXPORT["Local snapshot export"] --> STATIC["Static public demo<br/>Same interface, saved publications"]
    DB --> EXPORT
    CACHE --> EXPORT
```

The full application persists jobs, source provenance and versioned results. The static demo reads explicitly exported publications through a local adapter and cannot request new science. Source code lives in `backend/`, `frontend/` and `public-demo/`; maintained commands live in `scripts/`.

## Development checks

```bash
backend/.venv/bin/python -m pytest backend/app/tests -q
npm --prefix frontend run build
python3 scripts/check_vercel_clone.py
npm --prefix public-demo run build
```

TypeScript builds reject unused locals and parameters. Backend tests use isolated temporary databases and caches. Optional PostgreSQL tests require a dedicated `AF_TEST_DATABASE_URL` whose database name starts with `afterfire_test_`.

## Read more

| Guide | What it covers |
| --- | --- |
| [Operations](docs/OPERATIONS.md) | Provider access, historical imports, persistence, API and essential commands |
| [Scientific methodology](docs/SCIENTIFIC_METHODOLOGY.md) | Native grids, QA, seasonal references, harmonization, Reburn and limits |
| [Static demo](docs/VERCEL_CLONE.md) | Export allowlist, snapshot integrity, preview and hosting |

Developed by Ash Happens for NASA Space Apps 2026. AfterFire is an independent project, not an official NASA service or endorsement. Code is under the [MIT License](LICENSE); NASA data, geographic references and contextual imagery retain their respective [attribution and terms](docs/SCIENTIFIC_METHODOLOGY.md#visual-comparisons-limitations-and-attribution).

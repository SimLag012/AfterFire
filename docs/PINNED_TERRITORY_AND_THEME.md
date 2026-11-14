# Pinned territory and shared theme — 14 November 2026

The remaining discovery changes from `origin/main` at `432f0c0` are integrated, including the backend search implementation, packaged country bounds, stable/coarsening database clusters, search result extents and dynamic Return to place control. The locally requested single Explorer toolbar and full Data & Sources page remain in place.

## Selection and camera

`territory` stores the selected WGS84 rectangles (Leaflet latitude/longitude corner pairs), and `place` stores the display label. `map` and `z` store only the camera. Search extents are used exactly: camera padding is not added to the data selection. Searching `spagna` returns the full Photon extent `[-18.3936845,27.4335426,4.5918885,43.9933088]`, including the Canary and Balearic islands, and displays **Return to Spagna**.

Hotspot, indexed event and archive-cluster requests use the selected territory or explicit circle bbox, independently of camera pan. Camera zoom can change archive aggregation resolution while retaining exactly the same selection. Labels and selection persist through reload, shared URLs, saved-view restoration, event returns and Data & Sources navigation. Return to place fits the complete selected extent. Restoring a saved camera does not silently replace its selected territory. Delayed camera callbacks are fenced to the Explorer route so they cannot override navigation to another page.

The on-demand adapter keeps its existing 30° per-axis limit; large/component selections are split into bounded rectangles, and original observation IDs deduplicate across components. Partial/provider-limited responses remain partial. Existing persistent coverage cache is reused, but selected requests disable its former 8% acquisition margin and propagate cancellation. SQL archive endpoints accept an optional validated union of up to 64 rectangles; records in the gaps are excluded and overlapping rectangles do not double-count records. Country extents remain bounding rectangles, not political boundary masks.

The previous January/August calibration, Recovery formulas, QA, raster geometry and scientific publication code are not changed by this work.

## Shared visual theme

The warm dark palette in `styles/tokens.css` remains the source for Explorer, Data & Sources, event analysis and other pages. Legacy Slate utility surfaces now resolve to these same tokens. Calendar controls, borders, muted states and links use them, and chart tooltip backgrounds follow the same palette. Scientific heatmaps, confidence classes, index/map legends and series colors retain their distinct meanings. Print report styling remains a separate print-only presentation.

## Verification

- Production TypeScript/Vite and Docker frontend/backend builds pass.
- **295 SQLite and 295 isolated PostGIS tests pass**, including full Spain extent/alias and rectangle-union/no-duplicate/no-gap regressions.
- Desktop 1440×900 and mobile 390×844 tests use the actual place-search API and controlled hotspot fixtures to inspect HTTP scoping. They verify full-country framing and Return to place, **zero new hotspot requests on pan/zoom**, exact small-area requests without an acquisition margin, reload, saved-view restoration, Data & Sources return, common theme and no JavaScript errors. These fixtures are UI/query tests, not NASA completeness/calibration evidence.
- The existing real local-API browser flow checks cached authentic calendar data, supported anomalies, event Recovery/Reburn, preserved circles and period, saved comparisons and Data & Sources navigation. One initial run timed out waiting for Recovery Intelligence; the subsequent run with the known persisted event link passed. Final results are retained with the test logs.
- All **192 publications in the retained synchronization baseline** have unchanged payload fingerprints. The current inventory also contains two additional event analyses and two additional Recovery assessments; they are retained, not deleted or attributed to a scientific change here.

Reproducible scripts: `scripts/verify_pinned_territory.cjs`, `scripts/verify_unified_browser.cjs`, and `backend/app/tests/test_selected_territory.py`. Browser scripts use a separately installed Playwright/Chromium runtime via the existing environment variables. Execution evidence, screenshots, source backup and scoped secret scan are retained in `/home/simlag012/.codex/backups/afterfire-pinned-territory-20261114-171135/`.

All changes and commits remain local on `feature/fire-activity-intelligence`. No push, main merge, PR or remote deployment is performed.

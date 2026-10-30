# Italy explorer audit and verification — 28 October 2026

## Repository audit

The repository already contained uncommitted explorer, event-detail, archive import,
coverage and scientific changes. These were preserved and completed, rather than
replaced with another application. The inspected chain includes ExplorerPage,
LeafletMap, TerritoryPage, RecoveryPage, RecurrencePage, ComparePage, ReportPage,
DatasetsPage, TimelineBar, RecoveryChart, HarmonizedCalendarChart, router/client/types;
FastAPI routes, SQLAlchemy models, FIRMS/burned-area/vegetation providers,
harmonization/recovery/recurrence engines, import scripts and existing tests.

The original committed map fallback was Rhodes (36.125, 28.015), zoom 10;
there was no identified hardcoded Africa center. The uncommitted map already
introduced Italy bounds, but the Docker frontend at port 3000 still served an
older circle-only explorer. Thus source presence did not establish deployed
behavior. The final map uses Italy fitBounds, a definite responsive height,
resize invalidation, no maxBounds, no initial selected rectangle/circle, and
an explicit return action that clears the circle while retaining date/sensor
filters. The configured Sicily rectangle remains only a legacy analysis/provider
configuration; it does not constrain explorer navigation or local circle queries.

The local SQLite sample initially contained 1,522 synthetic rows and no real
Italian data. The configured Docker PostgreSQL contained 1,522 synthetic and 597
real rows. These were distinct databases: local SQLite experiments are not counted
as proof that the Docker application's archive was populated. Final coverage and
counts are taken from the configured PostgreSQL API.

## Changes verified by automated tests

30 backend tests passed on SQLite, and the same 30 passed on a separately created
PostgreSQL/PostGIS test database (`afterfire_test_explorer_20261028`). Tests never
use the configured production/archive database; explicit PostgreSQL test URLs
must name a database starting with `afterfire_test_`. Each session resets only
that test schema, and each test disposes its pool to avoid asyncpg event-loop reuse.

The tests cover existing health/datasets/area analysis, observation harmonization,
QA/scaling, recovery calculations and stable candidate IDs. Explorer tests cover:

- complete SQL aggregation beyond the previous 50,000-row cutoff;
- date/instrument filters, synthetic exclusion and empty unimported intervals;
- exact circle radius, rejection of the bounding-box corner, partial coverage;
- dateline-crossing circles and wrapped viewports;
- international empty results and locally available foreign observations;
- indexed candidate pagination, complete direct-link histories and stable IDs
  under changing date/sensor filters;
- import validation, Italy boundary exclusion, duplicate counts, idempotency and
  resumption after a committed chunk followed by an interrupted chunk;
- selection of Italy-only annual files from NASA's index;
- preservation of all members in dense 1,000-observation candidate groups;
- refusal to invent recovery baselines or use today's date for malformed data;
- unknown recurrence/recovery indicators when vegetation observations are absent;
- legacy alias deduplication while retaining revisions and original observations;
- native categorical VIIRS confidence without invented percentages;
- same-event-loop CLI resource cleanup, including failed imports.

The fixture records in these tests are synthetic and are not evidence of NASA
integration. NASA evidence is recorded separately in import checkpoints and the
real database coverage snapshot.

## Browser checks

Browser checks use the actual application interface. The standalone Playwright
connector could not start its missing Chrome binary, so checks used the app's
browser through CUA instead. The replayable CUA suite is `scripts/verify_explorer_ui.mjs`; its seven groups
of UI assertions passed on the running PostgreSQL-backed application. Results are
saved in `docs/explorer-ui-verification.json`. This requires a CUA browser session,
not an installed frontend CI runner. Reproduce these checks after starting the services:

1. Open `/explorer` with no parameters. Confirm Italy, Sardinia, Sicily,
   Mediterranean context, all dates, numbered clusters, legend, no selected area.
2. Verify 390×844 and desktop layouts. Pan and zoom outside Italy freely.
3. Choose a recent period outside the archive. Confirm zero clusters and no
   markers from the previous period; the active date range remains visible.
4. Set MODIS, VIIRS and all sensors. Compare counts with the same API filters.
5. Draw a circle using the center then its edge; edit coordinates/radius, then
   clear it. Confirm URL, contour, list and count track the selection.
6. Search 40.7, -74, radius 25 km. Confirm no Italian observations and the message
   “No data available in the current local archive for this area and period”.
7. Return to Italy. Confirm the circle clears and active date/sensor filters remain.
8. Select a candidate, show it on the map, open its direct URL, refresh it, and
   inspect before/fire/after/recovery dates. Explorer filters must not cut history.
9. On candidates lacking a study-area link, confirm vegetation and burned-area data
   are explicitly unavailable. No inferred NDVI, perimeter or recovery is displayed.

Browser verification exposed and fixed circle centering that attempted to read
bounds from an unattached Leaflet layer, and a mobile flex layout that left the
map at its minimum height with an empty gap. The return action and out-of-coverage
message were checked on the interface, not inferred from filenames.

## Real source and operational limits

Official annual source:
https://firms.modaps.eosdis.nasa.gov/data/country/yearly_summary_files.txt

Official API availability and area endpoints are queried with the existing key;
keys are not committed, printed in receipts or logged in request URLs. Download
receipts retain product, requested date window, file hash, counts and source URL
without credentials. The official annual index provides MODIS, Suomi-NPP and
NOAA-20 Italy files. NOAA-21 and missing latest years use availability-driven SP
and then NRT windows. Source `version` values are retained verbatim; annual MODIS
rows are labeled by the actual annual source rather than guessing a collection
from values such as `6.2` or `6.03`.

The first proposed SQLite relabel operation was rejected by automatic review for
insufficient scope/reference checks. It was replaced by a transaction enforcing
91,834 session-created rows, 18 matching checkpoints, original deterministic IDs,
Italy/non-demo provenance and zero referencing event links, with a verified SQLite
backup before changes. PostgreSQL was backed up separately before ingestion. No
user record deletions or database-volume resets were performed.

Available records and imported request/file windows do not establish complete
NASA historical coverage. Natural Earth's 1:10m boundary has cartographic coastal
uncertainty. Real MCD64A1/MOD13Q1 retrieval and spatial assignment to imported
hotspot candidates remain unavailable where no observations are linked. The
vegetation providers are import adapters, not verified live regional downloaders.
Greedy thermal grouping can include persistent non-wildfire sources; it is neither
DBSCAN nor an official fire inventory. The recovery baseline is a pre-event mean,
not a seasonally matched model. NDVI does not establish ecological recovery.

## Final populated archive

802,234 real Italian observations were verified through the running API. The job
added 801,642 rows, excluded 80,879 outside the Italy boundary, rejected zero invalid
rows and recognized 398 exact copies of existing legacy-source observations. All
597 original real rows (592 Italian) and 1,522 demo rows were preserved. A second
verified PostgreSQL backup preceded removal of only those newly imported exact
copies; no published event links referenced them. Different source versions or
scientific attributes remain distinct. All 499 annual/API input windows returned
already_complete on rerun, representing 498 unique content checkpoints (two
MODIS input windows had identical content). CLI cleanup completed without
event-loop errors. Full live API results are in explorer-api-verification.json.

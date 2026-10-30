# Observed burn episode reconstruction

Phase 6 separates FIRMS thermal observations (evidence A), algorithmic candidate groups (B), and QA-screened MCD64A1.061 burned cells (C). A candidate is not an official fire identity; a MODIS grid cell is not a fire perimeter. Only repeated C observations of the same native ground cell support repeated observed burning.

## Inputs and native identity

The analysis is bounded to the selected published event AOI and requested dates. PostgreSQL bounds FIRMS joins by date, bounding coordinates and the existing GiST geography index; exact AOI intersection follows the bounded query. At most 100,000 pertinent detections are admitted. NASA sources are bounded by product, native tile and interval, with the existing 400-granule resource limit. Nothing copies or rebuilds the FIRMS archive.

MCD64A1 uses the original MODIS sinusoidal CRS (R=6371007.181). Tile size is 1,111,950.5196666667 m; 2,400 pixels per axis yield 463.3127165278 m cells, approximately 0.214658669 km² each. The global cell ID is `(v*2400+row):(h*2400+col)`. Native resolution, CRS, rotation and integral affine offset must agree within 1e-5 pixel/metre comparison tolerance before matching. Subset origin never forms part of cell identity. WGS84 polygons are display transformations of native rectangles. AOI edge selection uses pixel centres consistently with earlier phases; reported area is full observed cell area, not fractional burned perimeter area.

MOD13Q1 children use 4,800 pixels per tile. Each 500 m cell corresponds to four native 250 m children through integer division of global row/column by two. Rounded longitude/latitude is never used to establish identity. Shifted or reprojected grids are rejected, without nearest-neighbour QA resampling.

## QA and dates

Strict inherited MCD64A1 policy: QA bit 0 land and bit 1 valid must be set; bit 2 shortened mapping period must be clear. Burn DOY must be 1–365/366 in the product year; uncertainty must be 0–100 days. Unburned cells contribute mapping coverage only when uncertainty is 0–100 and QA special-condition bits 5–7 are zero; sparse observations, poor separability, limit dates, water contamination and persistent-hotspot special codes do not establish complete mapped coverage. They never create burn episodes. Unknown/nodata observations are excluded. Burn date uncertainty is retained as nominal date ± product uncertainty days; this is not a calibrated confidence interval.

Product years and DOY are decoded separately from monthly file names. Dates are compared on the calendar, so month/year boundaries do not create new episodes. Duplicate `(native cell, nominal burn date)` observations are collapsed across months/subsets; source IDs are unioned and the largest uncertainty is retained. A positive observation and missing month are different evidence.

## Operational grouping

The engine creates connected spatiotemporal components: a cell is connected to itself and its four edge neighbours when uncertainty intervals are separated by no more than `separation_days` (default 32; configurable 1–180). Components can span months or years. This is an operational reconstruction rule, not a universal minimum fire interval. Tests compare 10 versus 32 days and overlapping uncertainty explicitly.

Disconnected patches can form different components within the same real fire. In the reference Sicily control, 94 cells split into 68- and 26-cell components during the same August 2021 interval. **This does not establish two distinct official fires or a reburn.** The repeated-cell count remains zero. Conversely, components on disjoint ground do not establish repeat burning, however many candidates exist.

Episode IDs hash the algorithm version, grouping threshold and sorted cell/date/uncertainty support. The history identity also includes the requested AOI/source publication fingerprint, parameters, source inventory and acquisition policy. Updates create new publications. `reburn-6.0.1` corrects cell popup date ranges to use the cell's own observations rather than the enclosing component extremes; early `6.0.0` development publications remain distinguishable. `reburn-6.0.2` tightens mapped-coverage QA, retains missing composite slots and completes cumulative trend/persistence windows.

## Association and ambiguity

A bounded FIRMS query supplies candidate context. A 500 m hotspot footprint must intersect observed burned cells and candidate dates must intersect episode uncertainty bounds. All plausible candidates are retained; more than one association is labelled ambiguous. No candidate is chosen as a definitive official identity, and candidate counts never increment burned-cell episode counts. Multiple components can share one candidate.

## Coverage and limits

Each month records the set of native QA-valid mapped cells. Requested missing months, per-cell mapped months, expected AOI cells and incompletely mapped months are retained. Source availability alone is not complete coverage. Histories with incomplete coverage or source failures are partial. Zero repeated cells cannot demonstrate absence of unobserved fires. Resource bounds are 5,000 burned cells and 200 components per history, plus the inherited vegetation observation limit.

A long connected temporal chain can merge otherwise separable disturbances; a spatial gap can split a fire. Neither rule resolves official fire identity. Subpixel burns, unmapped intervals and product omission errors remain possible. [Recovery Gap](RECOVERY_GAP.md) requires shared observed ground and safe temporal support.

## Primary sources

- [MCD64A1 Collection 6.1 user guide, section 3.1.2](https://lpdaac.usgs.gov/documents/1006/MCD64_User_Guide_V61.pdf): DOY, uncertainty and QA bit meanings.
- [MOD13Q1.061 NASA Earthdata](https://doi.org/10.5067/MODIS/MOD13Q1.061): 16-day compositing, native 250 m observations and QA layers.
- [NASA Earthdata](https://www.earthdata.nasa.gov/): access and product provenance.

Official documentation was checked on 29 October 2026. The DOI initially returned 403 through the document fetcher; the NASA Earthdata search entry was accessible. Scientific thresholds above are application conventions, distinct from NASA product specifications.

# Provider equivalence and publication preservation

## Live Earth Engine follow-up

After project/ADC configuration, both server probes passed against real data.
`scripts/verify_earth_engine_equivalence.py` compares every retained reference HDF
(48 MOD13Q1 and 3 MCD64A1) using matching date, Collection 061, tile, native
window, cell centers, all required raw/QA bands and unchanged QA masks. Final
comparison: all raw arrays and AOI values identical across all 51 sources.
No new HDF was downloaded. This establishes the tested dates/windows on
`h19v05`, not every pixel or revision of the global catalog.

The initial comparison found only masked MCD64A1 uncertainty on observed
unburned land: retained HDF `(BurnDate=0, QA=3, Uncertainty=0)` versus the
adapter's masked-band sentinel 255. Schema 2 restores zero only for observed
unburned mapped land with the masked uncertainty sentinel. Missing uncertainty
for burned or unmapped cells remains invalid; observed non-sentinel uncertainty
is preserved. A regression test covers all these cases. All 51 comparisons
were rerun after this fix; original publications were not modified.

See [live evidence](EARTH_ENGINE_LIVE_VERIFICATION.md). Statements about missing
project access in the earlier checkpoint below are historical.

The existing science remains the reference: native MODIS sinusoidal grid, exact Collection 061/product/date/tile, unchanged raw QA classes and fill values, scale factor, AOI mask, per-cell seasonal baseline, anomalies, BurnDate and uncertainty. Server-side averages are not substituted for native-pixel medians.

Controlled tests in `app/tests/test_api_first.py` verify integer raster publication, unchanged QA acceptance/calibration, aligned native windows, cache replay with no provider request, corrupt-asset rejection, pixel/request limits, incompatible ORNL collection rejection and absence of automatic HDF/AppEEARS fallback. Existing native-grid tests also reject shifted grids and invalid calibration. These are controlled fixtures, not new real satellite observations.

Before/after persisted-publication checks use `event-4a728489ea44ea85eab6a978870e0b06`. The actual publication present at audit has 166 NDVI and 166 EVI entries, 94 burned cells and 20.1779152898568 km². The request mentions an older 154/154 publication; no values were added or modified to force agreement. The pre-refactor payload digest is recorded in `api-first-reference-before.json`.

Live ORNL returned small real arrays but no explicit Collection 6.1 identity; equivalence is refused. Live Earth Engine is unavailable without an external registered project and runtime credentials. A future real comparison must compare identical dates/native cells and raw arrays, QA, transforms, valid masks, burned-cell IDs, statistics and anomalies, recording differences honestly. Do not mark provider equivalence established from HTTP 200 or from unchanged cached results.

Additional controlled Reburn tests verify identical native BurnDate/uncertainty reconstruction from an API subset and prove that missing sources cannot invoke HDF or AppEEARS, even if the legacy submission setting is enabled.

The follow-up setup audit confirmed the same reference SHA-256 before changes.
The owner confirmed that a Google project must still be registered. New setup,
redaction and first-error-stop tests are controlled software tests, not additional
NASA observations. The live diagnostic intentionally reports
`hdf_equivalence_verified=false`, even after a successful small probe. Compare
retained HDF raw bands, full QA, dates and aligned native cells before promoting
new Earth Engine publications; see [live setup](EARTH_ENGINE_LIVE_SETUP.md).

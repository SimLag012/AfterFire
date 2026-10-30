# Provider equivalence and publication preservation

The existing science remains the reference: native MODIS sinusoidal grid, exact Collection 061/product/date/tile, unchanged raw QA classes and fill values, scale factor, AOI mask, per-cell seasonal baseline, anomalies, BurnDate and uncertainty. Server-side averages are not substituted for native-pixel medians.

Controlled tests in `app/tests/test_api_first.py` verify integer raster publication, unchanged QA acceptance/calibration, aligned native windows, cache replay with no provider request, corrupt-asset rejection, pixel/request limits, incompatible ORNL collection rejection and absence of automatic HDF/AppEEARS fallback. Existing native-grid tests also reject shifted grids and invalid calibration. These are controlled fixtures, not new real satellite observations.

Before/after persisted-publication checks use `event-4a728489ea44ea85eab6a978870e0b06`. The actual publication present at audit has 166 NDVI and 166 EVI entries, 94 burned cells and 20.1779152898568 km². The request mentions an older 154/154 publication; no values were added or modified to force agreement. The pre-refactor payload digest is recorded in `api-first-reference-before.json`.

Live ORNL returned small real arrays but no explicit Collection 6.1 identity; equivalence is refused. Live Earth Engine is unavailable without an external registered project and runtime credentials. A future real comparison must compare identical dates/native cells and raw arrays, QA, transforms, valid masks, burned-cell IDs, statistics and anomalies, recording differences honestly. Do not mark provider equivalence established from HTTP 200 or from unchanged cached results.

Additional controlled Reburn tests verify identical native BurnDate/uncertainty reconstruction from an API subset and prove that missing sources cannot invoke HDF or AppEEARS, even if the legacy submission setting is enabled.

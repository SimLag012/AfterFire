# Google Earth Engine provider

Supported catalog identities are `MODIS/061/MOD13Q1` and `MODIS/061/MCD64A1`. The SDK dependency is installed in backend images but initialized only when enabled with a nonempty registered project ID.

1. Register a Google Cloud project for Earth Engine and obtain the appropriate access/eligibility externally. Follow the [official setup](https://developers.google.com/earth-engine/guides/access).
2. Configure Application Default Credentials for the backend/worker runtime (or a securely mounted service identity with appropriate access). Never commit a service-account JSON. Backend and worker both need access; local interactive credentials are not automatically available inside Docker.
3. Set `AFTERFIRE_EARTH_ENGINE_ENABLED=true` and `AFTERFIRE_EE_PROJECT_ID` in the private environment. Recreate backend and worker with the same configuration. No code here enables services, creates credentials or activates billing.
4. Preview a bounded acquisition plan, validate a small reference acquisition against native source cells and inspect provenance before relying on new publications.

The adapter uses date-specific images, a small projection metadata read and [computePixels](https://developers.google.com/earth-engine/apidocs/ee-data-computepixels) with a bounded grid and `NUMPY_NDARRAY`. The native `SR-ORG:6974` resolution and integer alignment are verified. Required raw bands are NDVI/EVI/DetailedQA/SummaryQA or BurnDate/Uncertainty/QA/FirstDay/LastDay. Missing pixels are filled with invalid QA/raw sentinel values before transfer, not plausible zero vegetation. Raw NDVI/EVI retain the original 0.0001 calibration applied downstream.

There are no exports or indiscriminate collection `getInfo()` calls. Projection metadata reads are bounded; API requests have a deadline and limited SDK retries. Request counts, bytes of decoded arrays and cache hits are exposed in provenance/progress. Exact wire-byte telemetry is not available through this SDK conversion and is not claimed.

This environment has no configured project/credentials. Live Earth Engine acquisition and provider-to-HDF equivalence therefore remain **unverified**. The offline controlled adapter tests do not constitute live provider verification.

See [live setup](EARTH_ENGINE_LIVE_SETUP.md) for the executable procedure and
`compose.earth-engine.yaml` for an optional read-only ADC secret shared by backend
and worker. `python -m app.providers.earth_engine_check --live` performs a bounded
historical probe through this same adapter; it never writes a publication.
The system health response exposes configuration separately from live verification.
Authentication, quota, request-budget and timeout failures stop the scientific
pipeline at the first failing granule rather than repeating them across every date.
Missing-image/band failures can still yield explicit partial science when other
valid observations satisfy the unchanged publication rules.

Catalogs: [MOD13Q1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1), [MCD64A1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MCD64A1).

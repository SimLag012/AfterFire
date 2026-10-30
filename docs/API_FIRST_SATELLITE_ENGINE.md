# API-first satellite engine

Normal `acquisition=auto` follows: persisted scientific result → verified existing sources/native subset cache → configured compatible Collection 6.1 API → explicit unavailable result. Existing scientific engines, QA, baseline, anomaly, recovery and reburn methods are unchanged. Cached HDFs may still be read locally; missing full tiles are never downloaded automatically by the default path.

`app/providers/api_subsets.py` implements native windows and the optional Earth Engine adapter. Geometry is projected to the original MODIS sinusoidal sphere, expanded by one 500 m cell to preserve whole burned-cell selection, intersected with the catalog tile and snapped to integer native offsets. Required raw bands are fetched together. No spatial resampling or substitute aggregate statistic is introduced. The existing native GeoTIFF adapter then applies the same per-pixel science.

Cache identity includes product, Collection 061, tile, date, integer window, affine transform, bands and adapter schema. Assets are integer GeoTIFFs, checksummed before cache hits, with atomic manifest publication under a cross-process file lock. Published results remain managed by the existing pipeline. Corrupt source assets miss cache and cannot silently become successful results.

Defaults:

```dotenv
AFTERFIRE_API_FIRST=true
AFTERFIRE_FULL_HDF_AUTO_DOWNLOAD=false
AFTERFIRE_SATELLITE_PROVIDER=auto
AFTERFIRE_APPEEARS_SUBMISSION_ENABLED=false
AFTERFIRE_ORNL_ENABLED=true
AFTERFIRE_EARTH_ENGINE_ENABLED=false
AFTERFIRE_EE_PROJECT_ID=
AFTERFIRE_API_MAX_REQUESTS=1000
AFTERFIRE_API_MAX_RESPONSE_MB=16
AFTERFIRE_API_MAX_PIXELS=100000
```

The existing job traffic budget, runtime limit, cache quota, disk reserve and download semaphore also apply. Each API window is checked before a request; compute results have a bounded native pixel count. Missing access, incompatible collection/grid, request/byte quota and provider errors are explicit. Earth Engine payload telemetry counts decoded raw-array bytes, **not exact HTTP wire overhead**. ORNL streaming telemetry counts received response-body bytes.

Advanced `acquisition=hdf` is an explicit full-source operation and retains the original budgets. The UI labels it accordingly. Enabling a provider never creates billing, credentials, exports, emails or AppEEARS tasks. Persisted result identities and scientific engine version remain unchanged to preserve previous publications.

See `EARTH_ENGINE_PROVIDER.md`, `ORNL_PROVIDER.md`, `PROVIDER_EQUIVALENCE.md` and `API_FIRST_VERIFICATION.md`.

Historical Reburn acquisition uses the same API-first plan and bounded native adapter. Existing HDF/AppEEARS/API sources are reused after integrity and AOI-coverage checks. The Reburn reader recognizes the API subset cache and holds the matching writer lock; it does not reinterpret API descriptors as AppEEARS manifests. Missing history has no implicit HDF or task fallback.

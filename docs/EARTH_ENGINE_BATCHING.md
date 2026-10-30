# Native Earth Engine temporal batches

[Performance report](ULTRA_FAST_ANALYSIS.md) · [Provider](EARTH_ENGINE_PROVIDER.md)

The adapter groups Collection 061 sources by product and native tile. Each source
retains its CMR identity, date and revision. A bounded Dictionary request verifies
every image projection; a versioned native-grid registry retains source-specific
CRS/affine/fingerprint evidence for 24 hours. Every reused transform is rechecked
against the native tile. Missing or shifted metadata fails; QA is never resampled.
The same geometry/tile window is reused through a bounded LRU.

Each date/band gets an explicit `dNNN_band` identity in a single computePixels
expression. The maximum is 32 dates, selected from the measured cases below;
capacity also respects 1024 bands, 32000 pixels/dimension, 48 MiB uncompressed
and the stricter configured response limit (16 MiB by default). A single source
uses the existing adapter. Source locks are acquired in sorted order and duplicate
IDs are collapsed; conflicting identities fail. Publication occurs only after
shape, integer-domain and byte-budget checks. SDK deadlines/retries remain 30 s/1.
Requests remain sequential; extra workers/accounts and larger timeouts were not
used. Shared quota accounting now scans once per temporal batch under the same
cross-process lock, with a conservative reservation for all source files.

| Maximum dates | Real seconds | Explicit metadata + pixel RPCs | Decoded bytes |
| --- | ---: | ---: | ---: |
| 1 | 45.5403 | 102 | 1073424 |
| 4 | 21.6254 | 26 | 1073424 |
| 8 | 13.3478 | 14 | 1073424 |
| 16 | 8.5169 | 8 | 1073424 |
| 32 | 6.4212 | 6 | 1073424 |

All 51 retained NASA HDF windows match every raw band exactly. The multi-date
cases each used an empty registry; the first one-date trial also had no registry.
Provider-side caches and load are uncontrolled, so these are descriptive trials,
not a statistically established optimum or p95. See [machine evidence](phase65-batching.json).
No high-volume/concurrency speedup is claimed. Those experiments remain open;
standard sequential requests already meet the isolated initial target.

Source cache schema 3 stores all raw int32 bands in one native multiband GeoTIFF,
with explicit band indices/descriptions and checksums. VI reads restore int16 only
after exact integer-range checks; this changes storage, not scaling or QA. Existing
schema 2 sources/publications are retained. Four/five raster opens become one per
read; all source datasets are closed together. No HDF is fetched automatically.

Remote reducers were not substituted: native arrays are required by spatial
recovery and reburn, and the measured payload is small. NumPy's existing exact
median/MAD/seasonal methods remain authoritative. No remote-median equivalence is
claimed. Byte figures are decoded arrays, not HTTP wire measurements.

```mermaid
flowchart LR
  Sources --> GroupByTile --> VerifyEachProjection --> BoundedBatch
  BoundedBatch --> IntegerBands --> AtomicSourceManifest --> UnchangedQA
```

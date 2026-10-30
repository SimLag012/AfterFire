# Direct NASA acquisition

Production order: retained scientific cache → verified native subset → saved extraction task output (read/resume only) → bounded original HDF via NASA CMR-discovered Earthdata HTTPS. New AppEEARS task submission is disabled by default. Reburn uses the same direct HDF cache/downloader and limits when historical acquisition is explicitly requested.

The existing Earthdata downloader is reused. It supports Earthdata token or SDK username/password authentication; secrets remain server-side. CMR validates product, collection version, tile identity and exact composite dates. HDF4 signatures, required SDS layers, native sinusoidal transform, scale, fill, QA and reliability remain subject to the existing scientific validators. Original complete HDFs are a controlled fallback, not a spatial-subsetting claim. No global discovery or download is introduced.

## Capability checks on 30 October 2026

| Access | MOD13Q1.061 | MCD64A1.061 | Decision |
|---|---|---|---|
| CMR LPCLOUD collection | C1748066515-LPCLOUD | C2565786756-LPCLOUD | Exact published HDF identities discoverable |
| Harmony `/capabilities?collectionId=...` | HTTP 200; no services; bbox/variable/dimension/temporal false | Same | No compatible subsetting service advertised; do not create Harmony processing jobs |
| Legacy LP DAAC Hyrax catalog | Connection timed out | Connection timed out | No successful DDS/array slicing verification; not enabled |
| Earthdata Hyrax generic collections route | Unauthenticated HTTP 401 | Same generic probe | Not evidence of product-level availability or scientific compatibility |
| CMR-advertised MOD13Q1 OPeNDAP granule DDS/DAS | Authenticated HTTP 404 for both metadata requests | No link advertised on sampled MCD64A1 granule | Partial arrays not verified; disabled |
| Direct HDF and retained native arrays | Supported by existing reader | Supported by existing reader | Default bounded acquisition path; real retained-array equivalence tested |

See `direct-nasa-capability-probe.json`, `harmony-collection-capabilities.json`, `direct-nasa-authenticated-access.json` and `direct-nasa-native-equivalence.json`, `direct-nasa-fresh-equivalence.json` and `opendap-array-probe.json` for scope and measurements. A generic HTTP 200 or successful signature probe alone is not treated as scientific verification.

[Earthdata Hyrax](https://opendap.earthdata.nasa.gov/) supports constraint expressions in general. [NASA's LP DAAC response](https://forum.earthdata.nasa.gov/viewtopic.php?t=6972) documents MOD13Q1 access problems. This installation did not obtain an authenticated DDS and exact QA/native-coordinate window from a working MOD13Q1/MCD64A1 OPeNDAP endpoint. Therefore there is no invented slicing adapter. [Harmony capabilities](https://harmony.earthdata.nasa.gov/docs#capabilities) were checked for each actual collection, rather than inferred from the existence of its API.

The host is local rather than an AWS us-west-2 processing environment. No temporary cloud credentials or speculative HDF4 range-array reader is added. HTTP byte ranges do not establish that compressed HDF4 scientific arrays can be efficiently read as native windows.

## Scientific equivalence and limits

Two exact reference granules were also freshly acquired using direct authenticated HTTPS: MOD13Q1 August 2021 (85,207,161 bytes) and MCD64A1 August 2021 (812,345 bytes). Each complete HDF is byte-identical to its retained original; native masks, transforms and all required bands match exactly at 376 vegetation cells / 94 burned-area cells. Transfer/write/quota-loop times were 79.817 s and 4.025 s, respectively. Private verification copies were removed after comparison. These measurements are not a full multiyear job duration.

Twenty real retained HDF/subset pairs across both products were checked at identical native pixel centres. Integer data and QA match exactly, vegetation statistics use zero tolerance, grid offsets allow 1e-5 pixels and cell areas 1e-9 km². A full offline source replay reproduces all 154 usable NDVI and 154 EVI observations, baseline/metrics and 94 burned cells (20.1779152898568 km²). No interpolation or new QA policy is introduced.

A fresh multi-year acquisition cannot be promised in seconds. If sources exceed a request/block budget, shorten the requested window explicitly; no silent truncation, oversized download, or AppEEARS fallback occurs. Live authenticated direct access and fresh full-array acquisition are reported separately in verification.

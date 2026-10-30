# API-first and Explorer verification — 2026-10-30

## Verified security boundary

Remote `SimLag012/AfterFire`, `main`, was audited before edits. There were no tags, PRs, forks, branch protections or rulesets. The owner confirmed a coordinated window with the other writer. `git-filter-repo` rewrote both published commits in a separate mirror. All 543 reachable local/mirror objects and 163 application file versions were checked; only the secret replacement was allowed. The push updated only `main` with an explicit SHA lease. A fresh GitHub mirror independently scanned 126 objects after the prevention checkpoint with no exact old-key match. All 289 original modified/untracked entries were preserved before functional work.

The old value was also removed from private `backend/.env`; backend and worker were recreated with an empty FIRMS key. AppEEARS submission is false, API-first true, full-HDF automatic transfer false, Earth Engine disabled/unconfigured. Private backup and residual-cache limits are documented in `GITHUB_HISTORY_SECURITY.md`. No claim of physical deletion from GitHub caches or other clones is made; credential revocation is not independently verified.

## Real 14.15 GiB case

`api-first-real-case.json` records the actual affected event `event-30c4892d8b3bb714175bb3b2247b7f87`:

| Measurement | Result |
| --- | --- |
| AOI | 23.535300201189006 km² |
| Interval | 2023-10-27 → 2026-10-30 |
| Catalog full-tile volume | 15,194,122,058 bytes (about 14.15 GiB) |
| Bounded native payload estimate | 1,796,288 bytes (about 1.71 MiB; estimate only) |
| Preflight elapsed | 1.772 seconds |
| Peak process RSS | 131,352 KiB (whole process, not an incremental allocation measurement) |
| Catalog metadata cache hits | 2 |
| Scientific provider requests / new scientific bytes | 0 / 0 |
| Cache size delta | 0 bytes |
| HDF stream calls / new AppEEARS submissions | 0 / 0 |
| Result | Explicitly unavailable: Earth Engine not configured; ORNL Collection 6.1 unverified |

The real Analyze job was also retried through the running API and worker. `api-first-real-analyze.json` records queue/worker transitions and an explicit failed state in 12.795 seconds, with zero transfer. It stops at planning with `provider_not_configured`; no incomplete analysis is described as successful. No quota was raised and no orders, emails, cloud exports or billing configuration were created.

## Scientific publication preservation

The reference event `event-4a728489ea44ea85eab6a978870e0b06` was read before and after the changes. The serialized result is **byte-identical**, SHA-256 `351b026453f1912204b29822bba6d1fed0c4ac1628432c7701a135563edb7d00`. It has 166 NDVI and 166 EVI entries, 94 burned cells and 20.1779152898568 km². This is the actual latest local publication, distinct from the older 154/154 publication described in the request. No observations or scientific values were fabricated to force agreement.

## Real API and performance observations

See `api-first-api-verification.json`. On the live PostgreSQL archive, the Italy viewport represented 802,239 observations with 31 aggregate markers in 7,443 response bytes. The cold request took 1.7786 s; the next bounded-cache hit took 0.0083 s. NOAA-21 filtering selected 86,998 observations. A narrow historical viewport returned 254 real detections; raw responses are capped at 2,000, with explicit truncation. Additional current-candidate linkage metadata is now included in hotspot popups.

Queries outside Italy and across the date line returned explicit archive-coverage information, not claims of no fires. Named search returned five actual Photon results, with cache reuse and attribution. Online FIRMS is intentionally unavailable until a new backend key is configured; it is not marked live-verified.

## Tests and browser checks

SQLite and PostgreSQL/PostGIS suites run against isolated disposable databases, never the archive. Both suites passed: **159 tests on SQLite (78.61 s)** and **159 on PostgreSQL/PostGIS (101.26 s)**. Logs are summarized in `api-first-test-results.json`. They cover the original scientific engine, SSE/progress, persistence, source integrity, cache replay, QA, native-grid rejection, recovery, comparison and reburn, plus the API-only acquisition boundary and native API history reader. Controlled adapter tests do not establish live Earth Engine equivalence.

Production TypeScript/Vite builds and backend/worker Docker builds passed. The final frontend multi-stage Docker build hit the host disk limit; after clearing only disposable Docker build cache, the already verified production bundle was packaged into the same nginx runtime stage. Database and scientific volumes were preserved. Browser checks use the running application and real archive: desktop and 390 × 844 responsive viewport, global search, date/platform filtering, saved/shareable views, timeline stepping, actual VIIRS popup and event navigation, EVI, before/after, Recovery Intelligence, Reburn and persisted NDVI raster overlays. Evidence and screenshots are listed in `firms-style-browser-verification.json`.

## Limits that remain real

- Earth Engine requires an externally registered project and securely supplied runtime credentials. Live computePixels and raw-array equivalence remain unverified here.
- ORNL returned real one-cell subsets and required bands, but did not identify Collection 6.1. Automatic scientific substitution is refused.
- Earth Engine telemetry counts decoded native payload bytes; exact HTTP wire overhead is not available through the SDK conversion.
- Global recovery products remain event-scoped. Persisted burned-area/NDVI/EVI overlays are available in Explorer; advanced recovery/reburn/gap layers remain in the existing event views.
- Recent online FIRMS requires a new key, supports bounded recent windows/viewports, and has body/row/request limits. It is not a replacement for importing missing historical coverage.
- Cluster cache freshness is bounded to 15 seconds per backend process. Photon is a moderate-use demo service without an availability guarantee; self-host or replace it for larger traffic.
- GitHub caches/other clones and credential revocation cannot be certified by a branch rewrite.

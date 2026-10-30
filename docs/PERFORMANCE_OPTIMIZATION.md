# Phase 6 performance and reliability

Measurements are observations of this machine and dataset, not service-level guarantees. The legacy Phase 5 reports are preserved.

## Integrity policy and measured bytes

The new shared integrity index covers both original HDF sources and AppEEARS subset files. Each entry binds SHA256, size, complete manifest entry/identity, validator version, device/inode, nanosecond mtime/ctime, and TTL. File change, manifest/identity change, untrusted checksum, validator change or expired evidence forces a complete hash. Native scientific validation remains mandatory before processing. Persistent cross-process `flock` deduplicates simultaneous verification; atomic rename publishes evidence. File generation is checked again after hashing/validation. Symlinks and malformed checksum identities are rejected.

Unlike the old AppEEARS implementation, preflight and downloader reuse the same evidence rather than hashing every annual bundle again. HDF acquisition also calls the same verified source lookup. Cache access no longer changes source mtime merely to mark a hit. Planning metrics separate calls, hits, hashes, hash bytes, hash time, stat time and lock wait. These hash-byte counters **exclude bytes read internally by scientific validators or raster decompression**; no claim is made that all filesystem IO is zero.

### Isolated benchmark

[64 MiB fixture evidence](phase6-integrity-benchmark.json), [reproducible script](../scripts/benchmark_phase6_integrity.py). All destructive modifications are in a temporary directory, never the real cache.

| Condition | Seconds | SHA256 hashes | Content bytes read by hash |
|---|---:|---:|---:|
| Cold integrity evidence | 0.370571 | 1 | 67,108,864 |
| Indexed reuse | 0.000681 | 0 | 0 |
| Same file, changed metadata | 0.385206 | 1 | 67,108,864 |
| Corrupt content | 0.381911 | 1, rejected | 67,108,864 |
| Four concurrent readers after repair | 0.370815 wall | 1 total | 67,108,864 total |
| New interpreter/worker | 0.604176 including startup | 0 | 0 |

Cold means absent integrity evidence, not a flushed OS disk cache. The restart check uses a fresh process and the same persistent directory. TTL/manifest/content generation checks are additionally covered by numeric tests.

### Real planner: comparable warm A/B and separate cold-evidence sequence

[Final alternating warm A/B](phase6-planning-benchmark.json), [script](../scripts/benchmark_phase6_planning.py). Same Sicily event, pre_years=2, post_years=10, as_of=2026-10-28, 168 source candidates / 3,893,173,170 logical cached bytes. Both arms start with HDF evidence and NASA metadata already populated. Three alternating pairs use the same files; no scientific acquisition, OS cache flush or destructive real-volume index reset.

| Fully warm condition | Wall median (range), s | Cache/plan median, s | Hash bytes per run | SHA256 calls |
|---|---:|---:|---:|---:|
| Legacy subset hash on every access | 0.6655 (0.5049–0.8019) | 0.5278 | 3,292,870 | 556 |
| Persistent manifest index | 0.5707 (0.4903–0.6814) | 0.5434 | 0 | 0 |

The overlapping ranges and slightly higher cache-stage median **do not demonstrate a stable warm-cache latency speedup** on this small-file workload. The reproducible benefit is elimination of content hashing, while still checking all 556 subset file generations and 51 original source identities. A prior per-file-only implementation also had variable warm overhead ([evidence](phase6-planning-per-file-benchmark.json)). The manifest index uses one evidence read per annual bundle, binds the entire manifest, and never extends unchanged evidence when one file changes. Metadata/validator/TTL changes force full revalidation. Historical batch readers hold sorted subset writer locks and reuse each verified manifest throughout that read, avoiding duplicate annual-bundle verification per monthly record.

[Separate initial sequence](phase6-planning-initial-benchmark.json): initial legacy pass 49.8413 s end-to-end / 43.3639 s cache-plan / 3,893,691,090 hash bytes; first indexed AppEEARS pass 1.3552 s / 3,292,870 hash bytes; subsequent indexed pass 0.9895 s / zero hash bytes. The initial pass populated HDF integrity evidence and incurred 6.1649 s of CMR HTTP. **That 43.36→0.94 s cache-stage change is a cold/warm evidence comparison, not an isolated implementation A/B speedup.** The older Phase 5 99.83/33.25 s report is historical and not a controlled baseline on today's filesystem state. The 64 MiB fixture above supplies reproducible cold/modified/corrupt/concurrent/restart cases without altering scientific sources.

## Disk policy

Inventory reports logical and allocated bytes, deduplicated by physical inode, volume free space and cache quota separately. Scientific categories A/B (published results/visual assets) remain protected. C contains reacquirable sources/subsets; D contains replaceable processed checkpoints; E contains temporary files.

Cleanup takes the exclusive nonblocking global usage lease and quota lock. Active readers/writers/planners prevent removal. Old temporary files become candidates only after a 24-hour grace period with no active usage lease; recent partial files, locks, provenance metadata, manifests, hardlinks and published assets remain protected. A second inode/mtime check fences the unlink. Dry-run reports total reclaimable bytes separately from selected bytes needed to reach the target. Real scientific-cache cleanup was never run destructively for testing. The final system-disk reserve rejection was resolved separately by deleting selected unused Docker build-cache records; active images, database and scientific volumes were preserved.

The administrator inventory additionally reports referenced visual assets, unreferenced assets/bytes, active job folders and equivalent scientific publications. Equivalent publications are retained; there is no silent rewrite of result IDs or automatic deletion of visual assets without a regeneration strategy. This is deliberately a reporting limit, not a claim that all occupied published space is reclaimable.

Subset bundle capacity is checked before opening a scientific transfer, followed by serialized per-chunk quota checks. Reburn preflight reports available, protected and currently recoverable bytes. If protected files consume the quota, the job fails with available/required byte information. Increasing quota or explicitly evicting replaceable sources remains necessary; publications are never deleted to satisfy a new request.

## Frontend

All page routes use `React.lazy` under an accessible Suspense status. Leaflet and Recharts are shared chunks; they are not bundled independently for every page. The Reburn panel itself is imported only when opened in Event Analysis. No historical raster stack is eagerly fetched.

Phase 5 documented an initial JS bundle of 1,015.40 kB / 289.56 kB gzip. The first controlled Phase 6 route split built an initial chunk of 277.62 kB / 90.79 kB gzip; the complete collection of lazy chunks was approximately 1.02 MB minified. That is a loading distribution improvement, not elimination of all downloaded code. The final deployed initial chunk is 277,914 bytes / 105,707 HTTP gzip bytes, with 27 JavaScript chunks totalling 1,039,317 bytes. [Bundle and actual HTTP verification](phase6-bundle-verification.json), [final build](phase6-build-final.log). With static gzip enabled, the first measured home route transferred 124,392 bytes over eight asset requests; Explorer/Recurrence additional transfers were 68,849 / 143,020 bytes in the same browser context. These are actual encoded transfers, including shared-cache effects. Browser measurements and total initial transferred bytes are recorded separately; the Phase 5 number is a historical report, not an isolated rebuild of the old tree, which contains extensive uncommitted previous-phase changes.

Browser checks exercise actual tiles, 94 native cell paths, all map layers, a cell click, EVI/composite synchronization, dedicated-route refresh and mobile width. The initial verification is [recorded here](phase6-browser-verification.json); it is not inferred from a successful build.

## Worker and resource reliability

No new job queue was added. Existing PostgreSQL owner fencing, leases and heartbeat protect publication. Source and result IDs stay separate. Connection pre-ping/recycle protect against stale pooled connections. `cache_io` shields native IO from cancellation until its thread finishes: cancellation of `asyncio.to_thread` alone does not stop disk operations, so releasing the cache usage lease immediately would be unsafe. A controlled cancellation test proves cleanup remains blocked until the thread exits.

New progress phases expose historical source search, reconstruction and vegetation/gap computation. Unknown work remains indeterminate; 100% is committed with the scientific result. Remote task IDs, transfer bytes, cached data and elapsed time survive the existing durable telemetry. Terminal SSE snapshots are reconnectable. Nginx retains the Phase 5 Docker resolver fix.

The real restart check preserved source/assessment/map/GeoTIFF/comparison fingerprints and 803,761 total FIRMS observations, 802,234 Italy observations: [evidence](phase6-persistence-verification.json). Controlled tests cover concurrent integrity access, source acquisition deduplication, job identities, result publication, partial results, cancellation and SSE. They do not establish throughput under massive multi-user load. CPU/RSS/resource limits and remote NASA latency are not represented as a universal benchmark.


## Fast analysis update — 30 October 2026

The 5% path included catalog/cache planning and upfront yearly AppEEARS task preparation. Implicit retries reran saved QA-partial results. Status previously deserialized full result JSON every poll. The fixes reuse publication IDs, make retries explicit and share verified derived rasters. See [before diagnosis](FAST_ANALYSIS_DIAGNOSIS_BEFORE.md) and [measured verification](ANALYSIS_PERFORMANCE_VERIFICATION.md).

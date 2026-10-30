# Fast analysis

The live Earth Engine follow-up now verifies server authentication and exact
native arrays against retained HDFs. New acquisitions remain explicit and
bounded; an event newer than published products can have real pre-fire data
while post-fire recovery remains unsupported. See
[current live measurements](EARTH_ENGINE_LIVE_VERIFICATION.md).

Analyze is an explicit POST. Opening an event performs read-only GETs, displays FIRMS immediately, and loads the latest saved scientific publication independently of NASA planning. Partial scientific results retain their original period and quality warnings. A FIRMS overview is never labelled a completed scientific analysis.

Normal Analyze sends `retry=false`: exact scientific configuration and event geometry reuse the existing publication/job. The primary-key identity plus conflict recovery and conditional retry prevent concurrent clicks from duplicating jobs. New identities include the linked FIRMS geometry and observation dates; validated legacy publications retain their IDs. Changed science parameters or engine versions create separate results. Acquisition preference remains part of the request identity for compatibility with existing publications.

Preview is optional. A missing-source request immediately returns a queued job; workers perform bounded planning in the background. Prior publications remain visible while it runs. Update missing observations / Retry failed analysis are explicit actions and preserve the previous publication until an atomic replacement succeeds.

Status/SSE select publication IDs rather than deserializing scientific result JSON. Result payloads and map assets load separately. Existing database indexes and fenced worker leases are retained. An indexed reference-event lookup measured 0.072 ms execution time; no additional index was justified by this plan.

Local processing retains integrity evidence and native vegetation checkpoints. Derived TIFF/PNG content is keyed by float32 input, shape, native affine transform and renderer revision. Integrity evidence verifies bytes before reuse. Identical outputs use hard links across job folders, preserving each publication's asset URL and avoiding another render or repeated whole-cache quota scans. Older published assets can seed this cache only after exact native float and preview-pixel comparisons. Cache misses still enforce disk and result quotas. No published assets are deleted.

See [verification](ANALYSIS_PERFORMANCE_VERIFICATION.md), [NASA acquisition](DIRECT_NASA_ACQUISITION.md), and [submission policy](APPEEARS_SUBMISSION_POLICY.md).


## API-first acquisition update (2026-10-30)

Normal Analyze now prefers persisted results and verified native sources/subsets, then configured compatible Collection 6.1 APIs. Missing data never triggers automatic full-tile HDF transfer or new AppEEARS submission. Scientific QA, baselines, anomalies, recovery and reburn calculations are unchanged. ORNL collection equivalence and live Earth Engine access remain explicit limitations. See [API-first engine](API_FIRST_SATELLITE_ENGINE.md), [provider equivalence](PROVIDER_EQUIVALENCE.md) and [verification](API_FIRST_VERIFICATION.md) for current behavior; older acquisition descriptions above are historical.

If a new analysis reports `provider_not_configured`, follow
[Earth Engine live setup](EARTH_ENGINE_LIVE_SETUP.md); the error now gives the
registration URL, required runtime settings and that guide. Configure and probe
both backend and worker. Cached publications remain readable while external
registration is pending. Do not repeatedly retry Analyze before registration and
authentication have succeeded.

# Diagnostic baseline (30 October 2026)

Read-only API/database inspection; worker stopped before implementing the policy. No analysis submitted to reproduce a notification-producing failure.

* `run_pipeline.report()` returns `5 + int(80 * completed_units / (total_records * 2))`. Before acquisition/processing completes any units, discovery, planning and every `AppEEARS.prepare()` run at 5%. The prepare loop submits all missing yearly blocks upfront. `extract()` subsequently polls remote tasks every 10 seconds, up to 1800 seconds. These are real remote waits, not React rendering time.
* Live event `event-0e53a2fe09462d51b10e79aa200ff875` had reached 12%: `subset_download`, 71 sources, 7 processed, 5 remote tasks, 937305 network bytes. This snapshot does not reproduce the earlier 5% interval or measure its individual durations.
* Reference event's previous persisted attempt: 88.61 seconds including 168 source cache hits, 3893173170 logical cache bytes, zero network bytes, 6 recorded remote tasks. Historical telemetry does not identify how many were newly submitted in that attempt.
* UI start always sends retry=true, so a legitimate QA-partial publication is explicitly requeued. Analyze requires a ready preflight even for a saved publication. Opening the page itself is read-only.
* Status deserializes the entire ~690 KB result on every poll/SSE iteration merely to report availability.
* Warm localhost requests before change: status 37.082 ms, result 200.141 ms. API measurements, not click-to-visible or job runtimes.
* Local manifests: 25 distinct task IDs, no duplicate names; remote read-only audit: 27 AfterFire tasks, no duplicate names. See JSON for periods, layers, AOIs and states. Equivalent requests with different AOI encodings require separate comparison.
* Existing integrity fingerprints, manifest evidence, NDVI checkpoints, primary-key job identities and fenced leases are preserved.

The root graphify output contains only an interpreter marker; no graph.json exists to query. Source inspection was used.

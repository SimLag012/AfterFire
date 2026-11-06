# AfterFire release verification — 2026-11-06

This report records new executions against `afterfire-clean`; previous reports remain historical evidence. Source checkpoint: `a600eb1`, initially one commit ahead of `origin/main`. No history rewrite, archive import, production-cache purge or new AppEEARS submission was used. Machine-readable evidence: [release record](release-verification-2026-11-06.json).

## A — Infrastructure

Docker Engine 29.9.2; PostgreSQL 15 / PostGIS 3.3; FastAPI API, persistent analysis worker and Nginx frontend run in the existing four-service project. Database TCP health, API HTTP readiness and ordered startup passed. The database has no host port; API/frontend bind to `127.0.0.1:8000/3000`. Both ADC mounts are read-only. Real Earth Engine probes passed separately in backend and worker; FIRMS authenticated and advertised 12 products. Configuration alone is never reported as an Earth Engine live probe.

Fixed the clean overlay's `restart: no`: all four services now use `unless-stopped`. Two startup executions preserved three scientific publications and both named volumes. Fixed executable Git modes for the startup/verification scripts. Docker boot enablement and permanent owner membership in the Docker group were explicitly authorized and applied; current-session access was granted by a socket ACL. Group membership takes effect in newly logged-in sessions. No permissive socket mode, remote socket or socket mount into a container was added.

A physical reboot and deliberate interruption during an active scientific job were not performed. Lease expiry/reclaim, heartbeat and worker contracts are exercised by regression tests; recreation verified saved-result survival. Do not equate these with a real power-loss test. Startup command and recovery details: [deployment notes](DOCKER_ENVIRONMENT_RECOVERY.md).

## B — Scientific validation

All hotspot queries use the bounded official FIRMS Area API, MODIS standard processing, with no global archive. New queries succeeded for Italy (21 detections / 2 candidates; 2021-08-01–03), Rhodes (30 / 1; 2023-07-20–22), Jasper (11 / 1; 2024-07-23–25), Kangaroo Island (13 / 1; 2020-01-02–04). Ocean, 79–80°N and 179°E–179°W queries returned zero detections with available coverage. These empty responses establish neither no fire nor satellite analysis at a nonexistent candidate. The 1990 period was explicitly rejected with HTTP 422. Dateline candidate geometry/native windows also pass controlled regressions; no dateline scientific publication is claimed.

| Event | New work in this release | Valid NDVI / EVI | Baseline entries per index | Burned cells / observed area |
|---|---|---:|---:|---:|
| Rhodes July 2023 | Re-read saved publication; new isolated cold/warm Earth Engine analysis; assessment rechecked | 64 / 64 | 41 | 134 / 28.7643 km² |
| Jasper July 2024 | New persistent worker publication and cache check | 6 / 6 (4 pre, 2 post) | insufficient | 32 / 6.8691 km² |
| Kangaroo Island January 2020 | New persistent worker publication, assessment and cache check | 56 / 56 | 40 | 112 / 24.0418 km² |

These are event-scoped candidates, not complete disaster extents or official perimeters. All publications are **partial**, retaining QA-rejected/missing composites. Rhodes and Kangaroo assessments publish supported below-reference evidence for both indices. Jasper deliberately reports insufficient seasonal-reference/post-event support; its sparse vegetation observations must not be promoted to a recovery classification.

MOD13Q1.061 uses native sinusoidal integer NDVI/EVI scaled by 0.0001, DetailedQA and SummaryQA (pixel reliability); nodata and strict land/cloud/aerosol/snow/shadow rejection remain unchanged. MCD64A1.061 retains BurnDate, Uncertainty, QA, FirstDay and LastDay and native 500 m cells. Seasonal medians/MAD use wholly pre-event composites, with no post-fire leakage or interpolation. Cold/warm science matches exactly for observations, metrics and burned cells; no deleted historical HDF was reacquired or newly compared.

Reviewed authoritative band/QA definitions: [MOD13Q1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1), [MCD64A1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MCD64A1). Live availability must come from the provider, not a hardcoded catalog end date.

Reburn: the saved Rhodes 2021–2024 publication survived recreation and was retrieved again: two observed episodes, zero repeated cells, `insufficient_evidence`, with incomplete mapping explicitly retained. This is a new persistence/read check of an earlier computation, not a new multiyear acquisition or proof of no recurrence.

## C — Performance

| Measurement | Pipeline | Request → science result | Repeat Analyze | Decoded scientific bytes | Explicit operation counter |
|---|---:|---:|---:|---:|---:|
| Previous Rhodes publication (historical) | 33.22 s | 41.331 s | 31.74 ms | 1,991,732 | 8 |
| New Jasper worker publication | 25.60 s | 31.472 s | 28.06 ms | 1,193,408 | 8 |
| New Kangaroo worker publication | 24.90 s | 30.420 s | 34.09 ms | 1,328,128 | 8 |
| New isolated Rhodes cold | 22.702 s | excludes queue/publication/browser | n/a | 1,991,732 | 8 |
| Same isolated cache, warm | 2.306 s | excludes queue/publication/browser | n/a | cache reuse | no new science |

The isolated cold run used a fresh `/tmp` cache and suppressed DB publication; production cache was retained. It used 11.114 s CPU, peak RSS 194,536 KiB, 71 sources, and had zero PNGs at scientific completion. Warm observations, metrics and burned-cell geometry matched exactly. This is not evidence that a code change made the original 41 s end-to-end trial faster: provider latency, cache state, events and process overhead differ. The batching/native scientific algorithms were deliberately retained.

Browser timing is recorded separately in the machine record: saved science visible and requested lazy frame loaded. It is not a new-analysis end-to-end browser benchmark. Wire bytes, provider-internal RPCs, p95 performance and in-flight peak container memory were not measured. The explicit counter is the maximum cumulative source counter, not a sum of every source counter.

Before recreation, idle samples were API 332.4 MiB, worker 229.5 MiB, DB 135.7 MiB and frontend 10.8 MiB. Shared Docker images total 2.696 GB; database size after new publications: 29 MB; both named volumes total approximately 418 MB including test/scientific state. Build cache about 2.29 GB, no prune. These snapshots are not peak-memory or unique-per-image totals.

## D — Frontend and global Explorer

Fixed unnecessary zoom/period-mode hotspot cache keys, the initial unrelated Italy request for a shared global view, non-atomic source switching, stale candidates when dates become invalid, overlapping status messages, misleading local-archive provenance in online mode, and incorrect fixed “2,000 results” text for candidate truncation. Provider CSV metadata failures now produce explicit HTTP 502 incomplete-query errors. Coverage identifies missing satellite/date combinations rather than claiming complete mixed-sensor coverage. Today/24h/7d/custom are available online; unsupported broad archive presets and unapplied circle controls are hidden in online mode. Online area selection is explicitly the viewport.

Real Chromium checks cover desktop 1440×1050 and mobile 390×844, real FIRMS candidates, source switching, selection, saved Recovery Story, lazy frames, EVI, Before/After, Recovery Intelligence and Reburn panel navigation; runtime errors and horizontal overflow are checked. Candidate identity depends on viewport membership; the browser uses the exact previously published Rhodes candidate for scientific-result verification. It never assumes a broader viewport yields the same candidate.

Global navigation is conditional on provider period/viewport limits; a broad query exceeding 30° asks the user to zoom. No exhaustive geographic completeness or official event-boundary claim is made. Legacy area-oriented pages remain available and require configured areas; the supported empty-install workflow starts in Explorer and selected event pages.

## E — GitHub release and gates

Repository: `https://github.com/SimLag012/AfterFire`, branch `main`. Publish `a600eb1` and the release hardening commit only by ordinary fast-forward push, after a fresh fetch. GitHub's eventual remote SHA is recorded in the delivery report, avoiding a self-referential commit hash here.

New regression results: **189 SQLite passed (18.84 s), 189 PostgreSQL/PostGIS passed (24.83 s)**. PostgreSQL used only `afterfire_test_release_20261106`. Existing deprecation warnings remain (about 52,500, predominantly SQLAlchemy/affine); no tests were disabled. TypeScript and the Vite production build passed, including Docker builds. Tests ran in isolated dependency environments because copied legacy virtualenv/bin links were unusable. The initial temporary PostgreSQL test copy omitted the tracked Italy boundary; it was restored before the passing complete run.

The existing secret scanner now also rejects ADC/private JSON material, credential filenames, database/scientific binaries and files above 10 MiB. Both staged and all-tracked scans are required. Private `.env`, ADC, credentials, databases and caches remain excluded. Existing untracked historical screenshots/reports are preserved and deliberately unstaged. No credential rotation or history rewrite was attempted.

`npm audit` on the locked frontend reports **4 advisory entries (1 high, 3 moderate)** affecting Vite/esbuild dev tooling and React Router. The production image serves static files via Nginx and does not run Vite/SSR; the event return URL is restricted to `/explorer`. A major Vite/Router migration was not mixed into scientific verification. These advisories remain open, so this report does **not** claim unrestricted public-internet production certification. Keep loopback deployment; resolve and validate dependency upgrades before broad exposure.

Reproduce bounded API/science checks using `python scripts/verify_release_global.py [--science Rhodes|Jasper|Kangaroo|Italy]`; outputs default to `/tmp`. For isolated cold/warm checks run `PYTHONPATH=/app python /path/to/scripts/benchmark_phase65_cold.py --event-id <persisted-candidate> --output /tmp/cold.json` inside the configured backend. Browser checks: `scripts/verify_release_browser.mjs`, with `PLAYWRIGHT_MODULE` pointing to an installed Playwright module. No required browser library was added to the application bundle.

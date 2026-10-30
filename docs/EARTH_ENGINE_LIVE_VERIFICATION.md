# Earth Engine live verification — 2026-10-30

**The live provider is operational in backend and analysis-worker.** Both
authenticate using the owner's existing ADC, read Collection 6.1, and acquire
bounded native arrays. A new event publication now exists. Its scientific state
is **partial**, because the selected fire is newer than published satellite
products. Partial publication does not establish burned area or recovery.

Machine-readable evidence: `earth-engine-live-verification.json` and
`earth-engine-live-equivalence.json`. All results below are measured; controlled
regression fixtures are not counted as real satellite observations.

## Infrastructure and security

Seven authorized settings in the ignored `.env` were updated: API-first enabled,
Earth Engine selected/enabled, the supplied real project ID, the external ADC
path, AppEEARS submission disabled and automatic full HDF download disabled.
All other environment lines were preserved. No project, key, IAM role, API,
billing account or paid service was created or changed by this activation.

The existing `compose.earth-engine.yaml` overlay was sufficient. Its resolved
configuration was checked before recreating only backend and analysis-worker
with `--no-build --no-deps`. Docker inspection verified a **read-only** secret
mount on each server and no ADC mount/environment on the frontend. The external
ADC file remains mode 0600. No volume or scientific data was removed.

Updated source was built on the existing backend image; dependencies were not
changed. The rebuilt image runs in both server services. Continue using both
Compose files for service recreations, as described in
[live setup](EARTH_ENGINE_LIVE_SETUP.md). Plain Compose omits the ADC overlay.

## Live probes and integration fixes

`python -m app.providers.earth_engine_check --live` passed in **both services**.
Each probe retrieved five historical images over the tiny configured test area:
three MOD13Q1 composites and two monthly MCD64A1 images, retaining original dates,
required bands, sinusoidal projection and native affine alignment. Each received
6,240 decoded array bytes through 12 explicit collection/projection/pixel calls.
Final elapsed times and whole-process peak RSS are recorded in the JSON report.

Two real integration defects were found and fixed:

1. The installed SDK requires an initialized request session before
   `ee.data.setDeadline()`. The adapter now initializes before setting its 30 s
   request deadline and one-retry policy. The previous order failed with an
   `AssertionError` before authentication. A regression test checks the order
   and reuse of the initialized SDK.
2. Earth Engine masks `Uncertainty` on some observed unburned MCD64A1 land.
   The adapter filled it with 255 while the retained HDF stores zero. The initial
   comparison found 1,028 such window cells, including 188 AOI cell-observations,
   across three monthly images. Every difference was in this one band; QA masks
   for positive burns already matched. Restoring zero on mapped unburned land
   also preserves valid unburned coverage for Reburn. Burned/unmapped cells with
   missing uncertainty remain invalid, and observed non-sentinel values are
   preserved. Cache schema 2 prevents reuse of older adapter output without
   deleting previous cache files. A regression test covers all four cases.

## Scientific equivalence against retained NASA HDFs

The read-only comparator `scripts/verify_earth_engine_equivalence.py` uses **all
51 retained full HDFs referenced by the original publication**, reading only
small native windows locally and through Earth Engine:

- 48 MOD13Q1 images, 2019-08-13 → 2021-08-29.
- 3 MCD64A1 images, 2021-07-01, 2021-08-01 and 2021-09-01.
- Tile `h19v05`; 18,330 AOI center-cell observations across these sources.
- NDVI, EVI, DetailedQA, pixel reliability, BurnDate, Uncertainty, QA,
  FirstDay and LastDay all compared in their raw integer domains.
- Source identity, Collection 061, dates, HDF calibration/fill metadata,
  sinusoidal grid, integer offsets, native resolution and AOI center masks
  retained. Scaling remains raw VI × 0.0001 exactly once downstream.

After the fix, **every raw value in every requested window matched**, including
all AOI cells; all unchanged QA masks matched. The final complete comparison took
76.2831 s, with 102 explicit projection/pixel operations and 1,073,424 decoded
array bytes. Comparator peak RSS was 179,648 KiB. No new HDF was downloaded.
This verifies the tested windows/dates and source revisions, not the entire
global archive. Baseline, median, MAD, anomaly and recovery algorithms were not
modified.

The original reference result remains byte-identical after activation and new
publication: SHA-256
`351b026453f1912204b29822bba6d1fed0c4ac1628432c7701a135563edb7d00`.
Its 166 NDVI entries, 166 EVI entries, 94 burned cells and
20.1779152898568 km² observed area were not replaced. The FIRMS archive remains
803,761 observations.

## Real event analysis and measured performance

Event `event-30c4892d8b3bb714175bb3b2247b7f87` is a real seven-detection FIRMS
candidate from **2026-10-27**, centered near 40.8303°N, 16.1642°E. The existing
failed job was retried once through the normal API and persistent worker queue;
leases, fencing, heartbeat, SSE and atomic publication were retained.

| Measurement | Real result |
| --- | --- |
| Requested period / AOI | 2023-10-27 → 2026-10-30 / 23.535300201189006 km² |
| Provider | Google Earth Engine for all 68 acquired source records |
| Worker pipeline elapsed | 294.41 s |
| Request-to-observed-publication wall time | 295.921 s |
| Source-request and cache-publication stages | 148.0874 s combined |
| Source identity/grid validation stages | 7.1818 s |
| Local raster QA, maps, baseline and indicators | 132.8966 s combined stage wall time |
| Explicit projection/pixel operations | 136 |
| Decoded native array bytes received | 1,517,760 bytes, about 1.45 MiB |
| Native request windows | 1,395 cells/date × 68 dates = 94,860 cell-observations |
| AOI center cells | 441 per date before QA |
| Derived map assets | 136 NDVI/EVI observation assets |
| Valid index observations | 67 NDVI + 67 EVI; 69 expected entries each retain explicit gaps |
| Source/cache inventory growth | 1,803,202 bytes across the primary analysis |
| Observed filesystem free-space delta | −4,689,920 bytes; includes filesystem/log overhead |
| Sampled worker-container peak memory | 136.6 MiB; a sampled container reading, not exact process peak RSS |
| SSE events observed | 294 |
| Second Analyze API response | 0.014 s, same job ID and attempt count; no new acquisition |
| New full HDF downloads / AppEEARS submissions | 0 / 0 |

Stage timings are sums of existing worker operation wall-time records, not CPU
time or isolated network latency. Source acquisition includes cache publication;
the JSON report retains the detailed stage breakdown. Explicit operation counts
exclude SDK initialization, credential refresh and internal retries. Byte counts
are received decoded NumPy arrays, **not exact HTTP body or wire bytes**. The
earlier 1.71 MiB planner figure remains an estimate and was not used as measured
traffic. The full-tile catalog estimate of 15,194,122,058 bytes was not transferred.

## Publication, dates and post-fire limitations

Live collection discovery found latest image dates of **2026-09-30 for MOD13Q1**
and **2026-08-01 for MCD64A1**. Thus there is no published event-period burned
mapping or post-fire vegetation composite for the October 27 candidate.

The published state is `partial`. It contains real pre-event vegetation history,
67 valid pre-event observations per index, no usable post-event observations,
and explicit missing/QA-rejected dates. Pre-event medians are NDVI 0.2883 and
EVI 0.1571. Analysis geometry remains a **provisional hotspot buffer**, not an
official perimeter or observed burned area. `observed_cell_area_km2=null` means
unknown; it must not be described as zero burned area.

Recovery Intelligence completed in 10.178 s using the new publication and no new
acquisition. Both indices classify as `insufficient_data`, with insufficient
evidence and zero supported post-event composites. Recovery or return to
reference is not demonstrated.

Reburn's cached-only run completed in 2.116 s with `partial` status and 37 missing
months. It has zero observed MCD64A1 episodes/repeated cells in the tested cache.
Its `possible_repeated_fire_activity` label is FIRMS context only, not confirmed
reburning. No real overlapping burned cells were available to establish a
repeat burn or Recovery Gap; absence of observations is not absence of fire.
Acquisition of a new historical interval was not requested by this check.

## Browser and regression checks

The running frontend was tested at 1440 × 1050 and 390 × 844. Live progress showed
Earth Engine, completed requests, byte counts and worker activity. Final checks
loaded **actual NDVI and EVI raster images**, Recovery Story, Recovery
Intelligence, expanded Reburn and Before/After. Post-fire/recovery navigation is
disabled when unsupported, and Before/After explicitly reports that comparable
pre/post observations are unavailable. Saved Analyze and reload reuse the new
publication without increasing attempt count. No horizontal overflow or
JavaScript page errors were observed. The frontend source was unchanged.

Full isolated regressions passed: **176 SQLite tests (27.00 s)** and
**176 PostgreSQL/PostGIS tests (32.84 s)**. The two new regression cases use
controlled fixtures; they are separate from the real probes, 51-source
equivalence comparison and new-event acquisition. Tests did not receive the ADC
secret or use the production archive as their test database.

No external authorization blocker remains for the tested API operations.
Scientific support for this recent event remains limited by actual product
publication dates. New post-event burned-area/recovery verification must wait
for those real products; no dates, measurements or conclusions were fabricated.

## Git state

To preserve the requested Git history, this follow-up creates no commit and
performs no push. HEAD remains `1db6a42fa8e84faa521787b1f3d8659db15d601e`.
The adapter fixes, tests, comparator and reports are saved locally; the private
`.env` and ADC remain outside Git. Existing untracked reports/screenshots are
preserved. Tracked/staged content passed the repository secret scanner and an
exact comparison against the private ADC token/secret values with zero matches.

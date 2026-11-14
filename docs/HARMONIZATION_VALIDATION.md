> **Follow-up, 14 November 2026:** the report below is the preserved initial pilot milestone. Current unified UX, larger sample acquisition, failed multiscale validation, current publication inventory and final test evidence are in [UNIFIED_EXPLORER_IMPLEMENTATION.md](UNIFIED_EXPLORER_IMPLEMENTATION.md). Initial sample counts below must not be read as the current archive inventory.

# Fire Activity Intelligence — reproducible validation report

Session: 2026-11-13–14 (Europe/Rome); NASA source snapshot: November 13 UTC. Work starts at commit `ac02204` on main and is isolated on
`feature/fire-activity-intelligence`. The user's pre-existing modified documents
and untracked scientific evidence were preserved. No remote push is assumed.

## Architecture and source evidence

An independent normalized observation/checkpoint store, bounded FIRMS adapter,
reference-scale estimator, calibration artifact, holdout evaluation, anomalies,
calendar, exports and Explorer overlay are implemented. Existing Recovery models,
formulas, event identities, geometry attribution and 30-day policy are unchanged.
The existing worker processes acquisition requests when Recovery has no queued job.

NASA sources and exact formulas are in [the methodology](MODIS_VIIRS_HARMONIZATION.md).
The live source snapshot and fixed sample design are retained in
`fire-activity/availability.json` and `fire-activity/sample-design.json`.

Sampling was fixed before retrieval: six 2° × 2° boxes, January and August in
every year 2019–2024. Italy is Sardinia, Mediterranean is Rhodes, Brazil is
central Mato Grosso, Australia is southeastern New South Wales, southern Africa
is the Kruger area, Northamerica is northern California. These are small regional
samples, not claims of national representativeness.

The sample contains **151,674 original NASA records**, **72 region-month pairs**
and **144 independently checked sensor-month aggregates**. No demo detections
enter these results. Each product-month records original counts, occupancy and
original-payload SHA-256 in its region/year/month JSON evidence file.

The verification script independently reconstructs projected cell/day sets from
original FIRMS CSV dictionaries, without calling the normalization/aggregation
functions under test. All 144 sensor aggregates match. A second independent
calculation verifies same-month anomaly medians from saved original aggregates.

## Calibration results

Reference: Aqua daytime occupied 10 km equal-area cell-days. Input: S-NPP SP
daytime occupancy density. Training has 32 region-months (2019–2022), disjoint
interval calibration has 8 (2023), temporal test has 8 (2024), geographic test has
24 from the two entirely excluded regions. Sample/model identities are in
`fire-activity/calibration.json`, also packaged in the backend module.

Selected constrained log-linear model:

```
a = 0
b = 0.7798607376511302
x = log1p(SNPP_cell_days * 10000 / bbox_area_km2)
predicted_Aqua_cell_days = expm1(a + b*x) * bbox_area_km2 / 10000
```

Training geographic cross-validation MAE: **25.1703** versus **45.2188** for
identity occupancy. There is no arbitrary raw VIIRS-count multiplier.

| Independent test | n | MAE | RMSE | Mean bias | Relative aggregate bias | Identity MAE | Empirical interval coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| Temporal, 2024 | 8 | 10.1184 | 19.1306 | -5.8154 | -19.7133% | 29.0000 | 87.5% |
| Geographic, excluded Northamerica + southern Africa | 24 | 18.5392 | 42.6398 | 0.0462 | 0.1154% | 53.3333 | 100% |

Units for MAE/RMSE/bias are reference occupied cell-days, not fires. The model
passes its predeclared pilot gates: improvement over identity, aggregate bias
within ±35%, and >=70% empirical interval coverage on both tests. No threshold
was adjusted to make these results pass. All fixed sample months, including
zero/low activity, were retained. Geographic errors can vary substantially;
aggregate error does not imply uniform local accuracy.

The nominal **80%** split-conformal log-residual quantile is
**1.175175977463808**. These are broad prediction intervals; users can see their
width rather than interpreting a calibrated point as exact. Applicable bbox areas
are **37,923.83–48,357.25 km²**, with S-NPP density in the training range
**0–251.9011 occupied cell-days per 10,000 km²**. Converted estimates are additionally restricted to January/August 2019–2024. Smaller/larger or otherwise
unsupported translations return null. Direct Aqua observations retain null
measurement-uncertainty bounds, rather than fabricated instrument precision.

The API separately exposes `viirs_on_reference_scale` with its interval even when
Aqua is available, allowing users to inspect the calibration alongside the direct
reference. The selected calendar value prefers the direct reference; it never
adds a translated estimate to it.

## Calendar, anomalies and exports

Six cached sample studies contain 12 complete months each (January/August over
six years); the remaining **60 months per study are explicitly not acquired**.
They are intentionally partial histories, never presented as six complete years.
All **72 supported same-month anomaly calculations** are compared against
independent medians with the target year excluded.

Concrete browser/API/CSV example: Brazil August 2024 has **194** observed Aqua
cell-days; its other five Augusts have median **130**, absolute anomaly **+64**,
relative anomaly **+49.2308%**. Original monthly records remain **1,364 MODIS** and
**5,742 VIIRS**; these raw counts are not the calibrated activity metric. The
browser's downloaded harmonized CSV retains 72 month rows and 60 empty values.

`check_fire_activity_exports.py` verifies every export family for all six studies:
raw-record counts from exported IDs, monthly sensor series, harmonized values,
independent coefficient/interval evaluation, anomaly medians and metadata. It
also checks repeated reads do not mutate calendar results. Actual byte counts,
row counts, digests and elapsed times are in `fire-activity/exports-verification.json`.

Desktop/mobile UI evidence also confirms that the pinned month replaces the timeline context and hides unrelated Explorer candidates/overlays; returning to Explorer restores them, and selecting the cached month again restores its records without acquisition. The final scope of candidate/Recovery navigation
is recorded in `fire-activity/browser-verification.json` and screenshots. Browser
tests use real acquired data, not intercepted API responses or demo fixtures.

## Recovery protection and regression

Before integration: the existing relevant Recovery/scientific suite passed
**114 tests**, 11.28 seconds. After integration, the combined scientific/activity
suite passes **126 tests** on each of SQLite and PostgreSQL/PostGIS; exact counts/times are in
`fire-activity/sqlite-tests.txt` and `fire-activity/postgis-tests.txt`.

Read-only before/after database fingerprints match for **165 scientific
publications**, **18 Recovery Intelligence publications** and **5 Reburn histories**.
No published payload changed. The independent retained-raster verifier additionally
passes **9 scientific publications** for selected Rhodes, Tunisia, Sardinia, Jasper
and Chips/Dixie candidates. Details and native-series/pixel checks are in
`fire-activity/recovery-independent-after.json`; the all-publication comparison is
`fire-activity/recovery-preservation.json`. No new vegetation provider acquisition
or retroactive Recovery publication was used for this verification.

The initial attempt to run tests inside the old deployed image found that it
predated the checked-out source and lacked geonamescache. The baseline was then
run in an image built from the current requirements with the current source
mounted. An initial all-publication raster replay was interrupted by deployment;
only the completed, scoped nine-publication replay is claimed as independent raw
verification. Fingerprints cover every publication, including the other cases.

No changes are made to `app/analysis`, existing provider formulas, Recovery job
publication, assessment/reburn computations or persisted geometries. Worker queue
integration adds only a fallback activity branch after the Recovery queue is empty.
The same 114-test Recovery suite took 11.77 seconds after integration versus 11.28 seconds before (the after run shared the host with validation, so this is not an isolated latency benchmark). This verifies preserved science; it does not establish every possible live
provider/job latency under arbitrary future historical workloads.

## Performance and operational findings

Daily per-window raw counts and satellite occupancies are precomputed in checkpoint
evidence. Calendar reads defer the raw observations column; early task checkpoints were explicitly upgraded with derived daily summaries while retaining their original observations and acquisition evidence. Detailed map and raw
exports explicitly read it. Calendar/chart assets are lazy-loaded on explicit panel opening (verified in the actual DOM: no calendar asset links before opening, JS/CSS links afterward). The panel bundle is 13.07 kB plus 2.38 kB CSS before gzip. The status poll is small, full calendars refresh on
state transitions, and map movement never launches historical acquisition.

The NASA quota service actually reported **5,000/5,000** transactions during
sampling; Area requests misleadingly answered `Invalid MAP_KEY`. Acquisition
remained incomplete and the resumed adapter now checks quota before uncached
transfers, reserving 500 transactions for other users/functions. Cache hits remain
available during quota pauses. A transient quota-status failure also paused and
resumed sampling. The final timed resumed validation pass is in `validation.json`;
it is not a cold-download benchmark of all 72 pairs.

A real browser batch acquired early MODIS history from November 2000 onward, and
correctly withheld Aqua-scale values before its reference era. Another explicit
one-month acquisition exercised partial coverage and resume. Exact states and
network/cache evidence are in the browser report.

Source CSV storage is bounded to 512 MiB and the independent activity observation
store to 256 MiB, enough for the retained six-region pilot; Recovery raster/cache
quotas are not changed. Integer/float-equivalent bbox cache keys reuse existing
sources. Checkpoint commits are fenced; interrupted acquisition retains completed
windows and a durable per-batch counter. Multi-worker source downloads serialize
using a shared file lock and recheck cache after waiting.

## Reproduction

Using the existing backend image and normal configured environment/network/cache:

```sh
# Inside backend runtime, with /app on PYTHONPATH and scripts/evidence mounted:
python /scripts/validate_fire_activity.py --output /evidence
python /scripts/publish_fire_activity_sample.py
python /scripts/check_fire_activity_exports.py
python /scripts/verify_fire_activity_recovery.py
python /scripts/scan_fire_activity_secrets.py

# Test against isolated SQLite (conftest never uses the user's archive):
pytest -q app/tests/test_fire_activity.py app/tests/test_scientific_boundaries.py \
  app/tests/test_scientific_engine.py app/tests/test_phase5_recovery.py \
  app/tests/test_phase6_reburn.py app/tests/test_post_fire_recovery.py
# PostgreSQL: supply AF_TEST_DATABASE_URL whose database starts afterfire_test_.
# Create that disposable test database first. Never point tests at production.
```

The coefficient artifact is deliberately versioned and reviewed; the validation
script writes its candidate artifact to evidence, rather than silently replacing
production calibration. To package it, copy the reviewed artifact to
`backend/app/fire_activity/calibration.json` and build the normal images. No secrets
or databases belong in Git. Frontend verification uses `npm run build` or the
normal Compose build. The scoped secret scanner's exact coverage/limitations and
findings are in `fire-activity/secret-scan.json`.

## Acceptance limits — do not hide these

This is a working, independently tested **bounded scientific pilot**, not proof of
a universally harmonized 2000–present global fire record. Specifically:

- Terra-only 2000–July 2002 is original data with an unavailable Aqua-scale metric.
- NRT, nighttime, NOAA-20 and NOAA-21 translations are not calibrated in v1;
  their original detections remain available. Recent dates can consequently be
  browsed without a harmonized number.
- No cloud-free observation opportunities, fire absence, physical fire count,
  true combustion, burned-area replacement or ignition forecast is inferred.
- Converted estimates support only the declared area/density domain, January/August and 2019–2024; outside-domain values are null. Full biome/season/multi-decade generalization and actual mission-era
  transition stability have not been established.
- Annual trend code is implemented but the fixed January/August sample does not
  contain full annual series; no real annual trend is asserted from this sample.
- Full historical acquisition is incremental and quota-limited, not an instant
  preloaded twenty-six-year catalog. Completed study refresh for subsequently
  reprocessed products and automated partition lifecycle management remain future work.
- The six cached studies remain partial by design. Completeness, quality and
  limitations travel with every API result and export.

Therefore the original request's universal/multi-decade acceptance criteria are
**not all marked satisfied**. The implemented territory → historical activity →
anomaly → original candidate → existing Recovery path is validated at the pilot
scope documented above. Broader scientific claims require additional independent
calibration/validation, not visual interpolation or invented zeroes.

## Local commits

- `66f04ef`: isolated acquisition, harmonization, calibration and API.
- `f571a70`: validated temporal/seasonal applicability and exact checkpoint export scope.
- `0aea60d`: Explorer calendar, original-data map, comparison and scientific downloads.
- `7664dcc`: separate pinned historical map/timeline context from original Explorer candidates; cached re-selection.
- `95b7ab8`: defer calendar/chart assets until explicit panel opening.

All commits are local on `feature/fire-activity-intelligence`; no push to main or other remote branch was performed. Documentation and reproducible evidence are recorded by the following documentation commit in the same branch.

## Expanded validation outcome, 14 November 2026

The all-month campaign is complete: 252 region-month units / 292,401 original NASA records. Its pooled model is rejected (temporal relative bias −36.0816%; geographic interval coverage 67.8571%). The thresholds remain |relative bias| ≤35%, interval coverage ≥70%, MAE no worse than the identity cell-day baseline, and the predeclared minimum independent test support.

Exploratory calendar strata preserve those folds/gates and expose failures and insufficient support. A separate prospective June confirmation freezes the summer candidate before retrieving previously unseen June 2022/2025 for all six original regions. All twelve units are independent of that candidate's training, interval calibration and previous tests. It too fails: geographic relative bias +43.2180%. No failed or retrospectively explored candidate is installed in production. Exact metrics, coefficient fingerprints, original-record hashes and frozen designs are in `unified-explorer/seasons/` and `unified-explorer/june-confirmation/`.

The combined 264 units / 301,575 original records support broader actual observed coverage, not an all-season or universal conversion claim. The unchanged January/August pilot is the released VIIRS conversion. Raw data, directly observed Aqua values and explicit mission/scale gaps remain available. SQLite/PostGIS, real browser, independent CSV/coordinate replay, payload/raster fingerprints, native Recovery replay and measured performance evidence are detailed in [the implementation report](UNIFIED_EXPLORER_IMPLEMENTATION.md).

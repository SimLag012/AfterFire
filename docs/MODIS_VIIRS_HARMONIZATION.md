# Fire Activity Intelligence — MODIS/VIIRS harmonization

Implementation version: `fire-activity-1.0.0`. This is a separate thermal-activity
model. It neither consumes nor changes published vegetation recovery results.

## Source access, scope and provenance

Sources verified on 2026-11-13:

- [NASA FIRMS Area API](https://firms.modaps.eosdis.nasa.gov/api/area/):
  geographic bounding box, product, inclusive start date, 1–5 day windows.
- [NASA product availability](https://firms.modaps.eosdis.nasa.gov/api/data_availability/):
  query before acquisition; do not assume fixed current endpoints or mission dates.
- [NASA MAP_KEY quota](https://firms.modaps.eosdis.nasa.gov/api/map_key/):
  free key, 5,000 transactions/10 minutes; transactions can exceed HTTP request counts.
  The same-site `mapserver/mapkey_status/?MAP_KEY=…` service reports account usage.
- [NASA archive export](https://firms.modaps.eosdis.nasa.gov/download/):
  Earthdata/email authentication, bounded archive requests. This implementation
  does not automate account creation or download annual global archives.
- [NASA missing-data table](https://firms.modaps.eosdis.nasa.gov/api/missing_data/):
  lists known missing dates, but failed to expose its data during this verification.
  The table is not a cloud-free opportunity mask.
- [MODIS Collection 6/6.1 fire user guide](https://www.earthdata.nasa.gov/s3fs-public/2023-09/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf):
  sensor/algorithm limitations and obscuration.

The live availability snapshot is `fire-activity/availability.json`. MODIS SP
begins 2000-11-01; S-NPP SP 2012-01-20; NOAA-20 SP 2018-04-01;
NOAA-21 SP 2023-03-01. These are archive endpoints, not guaranteed valid
observations everywhere. Snapshot current endpoints matter: S-NPP NRT ended
2026-11-02 in the actual availability response. No continued S-NPP service is assumed.
All four satellite product families can be acquired, but only the calibrated
reference/input satellite pair can contribute to a translated metric.

Use NASA's open Earth observation data with NASA LANCE FIRMS/product attribution.
The repository software license does not replace the data provider's citation
requirements. No credential, authenticated URL, database, or raw global archive
is included in the scientific evidence.

## Observable and grid

For each satellite, day and grid cell, count occupancy once if at least one
**daytime** detection occurs. Retain night detections in the original-data output.
Use a fixed global EPSG:6933 cylindrical equal-area grid with 10,000 m edges:

```
cell = (floor(projected_x / 10000), floor(projected_y / 10000))
O(s, month) = cardinality{(cell, UTC day): daytime detection by s}
```

Grid origin and projection are fixed across regions and years. Latitude does not
shrink the cell area. This is occupancy of detected activity, **not** physical
fire count, burned area, FRE, or a corrected estimate of combustion. A detection
is assigned by its reported centre, not spread over an invented footprint.
Footprint scan/track and nominal sensor resolution are retained for inspection.

The reference is MODIS **Aqua daytime** occupancy. Terra is not concatenated with
Aqua, and the growing VIIRS constellation is not summed into the metric. An entire
MODIS SP month successfully acquired after August 2002 supplies the directly
observed reference. Terra-only early months retain original observations but have
`reference_not_yet_available`, not a manufactured Aqua zero. July 2002 is withheld
because it is not a full reference month.

A successfully queried archive with no detections has zero observed occupancy;
it does **not** establish cloud-free coverage or absence of burning. The returned
`observational_coverage` is null. Archive fractions measure acquisition, not clear
sky, overpass count, detection probability or land area surveyed.

## Translation and model selection

Let A be selected bbox geodesic area in km², V the S-NPP daytime occupied cell-days,
and M the Aqua value in the same complete SP region-month:

```
x = log(1 + V * 10000 / A)
y = log(1 + M * 10000 / A)
y_hat = a + b*x,  a >= 0, b >= 0
M_hat = max(0, exp(y_hat) - 1) * A/10000
```

Fit constrained least squares using `scipy.optimize.nnls`. Compare against
identity on cell-day density, not raw hotspot count ratios. Select between these
two predeclared candidates by leave-one-region-out MAE **inside training data**.
There is no manually chosen VIIRS multiplier. A single small model is evaluated,
not asserted to be universal. Satellite/processing/daytime strata are fixed;
NOAA-20, NOAA-21, Terra, nighttime, and NRT have no fitted translation in v1.

The six-region fixed sample is defined in `scripts/validate_fire_activity.py` and
`fire-activity/sample-design.json`: January/August, every year 2019–2024, all six
regions, including empty and unfavorable periods. It is a reproducible pilot,
not validation over all biomes, seasons, areas or the whole MODIS record.

Training: 2019–2022, four regions. Interval calibration: 2023, those regions.
Temporal test: 2024, those regions. Geographic test: all sampled years from
Northamerica and southern Africa (lexicographically final two region IDs).
No held geographic region enters fit, model selection, or interval estimation.

Report MAE, RMSE, mean signed error, aggregate relative bias, identity MAE and
prediction interval coverage for both tests. Deployment gates are predeclared:
MAE no worse than identity (1e-9 numerical tolerance), absolute relative bias <=35%,
and empirical interval coverage >=70% on **both** holdouts. Failure produces
`validation_failed`; the API refuses S-NPP translation, while original data and
the direct Aqua reference remain inspectable. Report failure honestly; never
change gates after examining a holdout to make it pass.

## Uncertainty and applicability

On the disjoint interval-calibration set, compute absolute log-density residuals.
For nominal 80% split-conformal intervals, take ordered residual at
`ceil((n+1)*0.8)` (n=8 in the fixed design). Backtransform both endpoints and scale
by A/10000. This is a prediction interval, not instrument measurement accuracy.
Exchangeability is imperfect for correlated remote sensing data; heldout empirical
coverage is reported. A direct reference observation has null lower/upper bounds
because its physical detection uncertainty is not measured.

A translated estimate additionally requires a whole S-NPP SP month, a validated
artifact, and both density and area inside the training ranges, a January/August calendar month, and a year inside 2019–2024. Other seasons/years are explicitly outside the validated conversion domain. Areas outside
those ranges, including most very small selections, return an explicit unsupported
state. Each complete S-NPP month also exposes `viirs_on_reference_scale` separately, even when a direct Aqua reference is available. This allows paired verification of the implemented translation; the two values are never summed. No coefficient is extrapolated to tiny or continental territories. Model
ID, sample digest, coefficients, training years, holdouts, errors, parameters and
limitations accompany every calendar result. Model versioning never changes
Recovery versions or checkpoint identities.

Important remaining limits: cloud/smoke/canopy obscuration, missed overpasses,
orbit drift, diurnal evolution, FRP differences, industrial thermal sources,
confidence differences and nonstationarity are not solved by this proxy. No
true opportunity normalization or sensor sensitivity inversion is claimed.
Before scientific use beyond the pilot, add independently validated strata and
broader spatial/seasonal/temporal samples. Pre-2019 stability and instrument-era
discontinuities are not comprehensively validated by this sample.

## Anomalies and trends

For a target calendar month, require at least five **other complete years** of
that month, with the same direct/translated regime and calibration ID. Exclude
target year. Report median B, absolute departure H-B and relative percent
100(H-B)/B only for B>0. Unsupported periods and partial months never enter the
baseline. This retrospective reference may include later years; it is not a
prospective prediction model.

Seasonal distributions report medians and quartiles after >=5 comparable direct
reference months. Annual totals require all 12 months. Annual Theil–Sen slopes and
95% slope intervals require >=8 complete direct-reference years; do not connect
partial years or substitute zero. No ignition prediction is provided.

## Isolation and persistence

Code: `backend/app/fire_activity/`, schema `backend/app/models/fire_activity.py`.
Tables: `fire_activity_studies`, `fire_activity_windows`. A window records bbox
hash, product, dates, explicit state, original observations and acquisition proof.
Window evidence precomputes daily raw counts and satellite occupancies so calendar reads defer the raw JSON column; month maps and exports read originals explicitly. Original JSON contains every NASA field; UTC timestamp, raw confidence, FRP MW,
scan/track, satellite, processing, product version and deterministic IDs are added.
Identical records deduplicate; different original scientific payloads remain
separate revisions. SP supersedes NRT on a satellite/day for derived occupancy,
while both remain in original exports.

The existing analysis worker services activity requests only when no Recovery
job is waiting and yields priority at each checkpoint. It reuses provider CSV
cache, locking concepts, worker process and database pool. A separate acquisition
request table is necessary because the existing Recovery job table requires a
non-null fire-candidate FK; no artificial fire candidate is inserted to run an
activity request. Scientific publication/assessment/reburn queue logic is unchanged.

Transactions atomically fence checkpoint publication with request owner/lease.
Expired activity leases resume after restart. Complete windows are reused; failed,
truncated and unavailable windows can be retried explicitly. There is no periodic
whole-history catalog scan. Account quota is checked before uncached transfers,
with a 500-transaction reserve. Local transfers serialize across worker processes.
The activity observation store is capped at 256 MiB; shared root provider CSVs at
512 MiB; neither policy deletes Recovery rasters or cache. Administrators should
export/archive old studies when the bounded pilot store fills. Automatic long-term
partitioned archive lifecycle management is not implemented.

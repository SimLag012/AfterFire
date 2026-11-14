# Historical Fire Activity Calendar

The existing Explorer map now has a **Fire activity** toolbar control and overlay
panel. No new primary page or alternative recovery pipeline is introduced.

1. Select the existing geographic region, enter a circle, or draw it on the map.
   The activity selection is explicitly its **bounding box**, including corners.
2. Open Fire activity, set an independent historical start/end date (2000-11-01
   through today), and click **Acquire history**.
3. A background request acquires at most 28 five-day product windows per batch.
   Use **Resume missing windows** to continue. Complete windows are never fetched
   twice on refresh. Panning does not launch historical acquisition.
4. Read rows of years and January–December columns. Yellow/red is supported
   reference-scale activity; pale zero is zero in acquired reference data;
   gray means missing/unsupported, and striped cells mean partial acquisition.
5. Each cell has keyboard focus and a tooltip with value, sensors, archive
   completeness, interval and unknown cloud-free coverage. Click for original
   MODIS/VIIRS counts, anomaly support and original hotspot locations on the map.
6. Expand monthly charts to inspect the metric with gaps and independent original
   sensor count bars. Compare selected months only within compatible regimes.
7. Follow an existing persisted candidate link to Recovery Story. Alternatively
   choose a seven-day window and **Explore original candidates** in the existing
   on-demand Explorer; this preserves its established grouping, identity,
   geometries and explicit candidate-selection workflow.

The calendar can inspect recent data, including events younger than 30 days.
Recovery continues to enforce its existing minimum age. It is not automatically
triggered by acquisition or month clicks. While a calendar month is pinned on the map, unrelated Explorer candidates and scientific overlays are hidden and the bottom timeline displays the historical month; returning to Explorer restores the original filters and candidates. Newly inferred calendar event geometries
are deliberately not substituted into Recovery.

The panel stores the last study ID on the device; reload retrieves cached results.
The displayed study bbox stays visible when the map selection changes, so old
results cannot silently appear to describe a new region. Reacquisition is explicit.
A current study is polled through a small status endpoint; full calendar responses
are refreshed at state transitions, not on every five-day checkpoint.

## API v1

All routes below use `/api/v1/fire-activity`:

| Method | Path | Purpose |
|---|---|---|
| GET | `/sources` | NASA product availability, quota, source metadata |
| GET | `/studies` | List up to 100 cached study scopes and states |
| POST | `/studies` | Explicit validated bbox/date acquisition request |
| GET | `/studies/{id}/status` | Small durable worker state and progress |
| GET | `/studies/{id}` | Monthly/annual metrics, anomalies, provenance, calibration, seasonal/trend statistics |
| GET | `/studies/{id}/months/YYYY-MM` | Original records and unchanged eligible candidate links |
| GET | `/studies/{id}/export/hotspots` | Original filtered normalized records, including original JSON |
| GET | `/studies/{id}/export/modis` | MODIS original monthly record counts and per-satellite occupancy |
| GET | `/studies/{id}/export/viirs` | VIIRS original monthly record counts and per-satellite occupancy |
| GET | `/studies/{id}/export/harmonized` | Reference-scale values, intervals and explicit unavailable states |
| GET | `/studies/{id}/export/anomalies` | Baselines, support, absolute/relative anomalies |
| GET | `/studies/{id}/export/metadata` | Machine-readable methodology, parameters, area, interval and per-product completeness |

Example request:

```json
{"bbox":[8,39,10,41],"start_date":"2019-01-01","end_date":"2024-12-31","window_budget":28}
```

Repeating the same bbox/date request resumes a partial job. Hashes include region,
interval and methodology version. A completed historical study is read-only on
repeated requests; newly released provider revisions require a new acquisition
scope/version (an explicit refresh/revision workflow is not yet implemented).

Optional `?month=YYYY-MM` filters CSV exports. Every CSV carries area, interval,
provider, units, method and parameters; metric exports carry quality and intervals.
Missing values are empty CSV fields, not zero. Maps and raw exports use the same exact checkpoints as the calendar; unrelated partial-window acquisitions in overlapping studies cannot change its reported counts. The metadata JSON includes all
product completeness states. CSV formula prefixes from string fields are escaped.
A response/record limit fails a window rather than labeling truncated records
complete. Month maps are bounded to the first 20,000 original records, with an
explicit truncation marker; CSV exports contain all acquired records.

## Acquisition/quality semantics

- `complete`: bounded provider request fully parsed and retained.
- `no_detections_in_verified_coverage`: valid full **archive query** returned no
  rows; the metadata expressly excludes clear-sky observational completeness.
- `partial`: record/body/store limit or malformed observation; never eligible for
  calibration or a complete metric month.
- `not_acquired`: no successful checkpoint yet.
- `provider_unavailable`: auth, quota or service failure; raw evidence includes a
  safe status/retry hint, never credential-bearing URLs.
- `not_available`: requested interval not inside that product's availability.

Monthly product fractions count successfully acquired days against **all days in
the calendar month**, including partial selection boundaries. Original raw zero
counts are null when nothing from the sensor has been acquired. A month metric is
complete only when its required reference/input product has all month days and a
supported scientific regime. Completing a request is different from having an
interpretable harmonized value in every requested month.

## Deployment

The normal backend/frontend and existing analysis-worker images include the
module. Run the existing Docker Compose configuration and its usual environment
and credentials overlays. `init_db` registers only two additional activity tables;
no vegetation-table or publication migration is introduced. SQLite and PostgreSQL
use identical JSON/checkpoint logic. No new service is required.

The implementation is a bounded pilot store, not an unlimited multi-tenant global
archive. Antimeridian requests must be split; geographic requests are limited to
±85° latitude, <=30° per axis and <=2 million km². Very small areas work on the
observed reference but cannot receive an extrapolated VIIRS conversion. Quota
failure leaves a partial request that can be resumed after NASA's 10-minute
interval; UI does not promise instant completion.

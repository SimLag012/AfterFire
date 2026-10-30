# Earth Engine activation evidence — 2026-10-30

**Activation is incomplete: external project registration is required.** The owner
confirmed that a Google Cloud project still needs registering. No project ID,
Google ADC file or Earth Engine user credential was found in the audited host
locations or server containers. No billing, service account, key, export or remote
processing order was created. Follow [live setup](EARTH_ENGINE_LIVE_SETUP.md).

## Infrastructure and software changes

Backend, worker, PostgreSQL/PostGIS and frontend are running. The existing
Explorer, scientific methods, persistent queue, fenced leases, SSE, source cache
and publication identities are retained.

- Optional `compose.earth-engine.yaml` mounts an existing private Google
  credential file as a read-only secret on backend and worker only. The normal
  Compose configuration continues to work without that file.
- Health reports configured/selected settings separately from live access. It
  neither authenticates nor labels a configured project as connected.
- `python -m app.providers.earth_engine_check --live` uses the existing adapter
  for bounded historical collection discovery, band metadata and native pixels.
  Without `--live` it performs no network access. Neither mode publishes science.
- Missing configuration errors identify registration, runtime settings and the
  setup guide. Authentication, quota, request-budget and timeout failures stop at
  the first failed granule, preserving completed source caches/checkpoints.
- Google credential JSON, private keys and certificates are excluded from the
  backend Docker build context; common credential filenames are Git-ignored.

Both deployed server runtimes ran the diagnostic with `--live`. Both returned
`blocked / provider_not_configured`, with authentication unverified, no collection
reads and zero decoded satellite-array bytes. This is evidence of an unavailable
provider, not a successful live scientific test. Exact reports are in
`earth-engine-activation-verification.json`.

## Scientific verification

The existing publication for `event-4a728489ea44ea85eab6a978870e0b06` is
byte-identical before and after backend/worker recreation:

```text
351b026453f1912204b29822bba6d1fed0c4ac1628432c7701a135563edb7d00
```

It retains 166 NDVI entries, 166 EVI entries, 94 burned cells and
20.1779152898568 km² observed cell area. No raw values, masks, scale factors,
baseline windows, MAD, anomaly, recovery or reburn methods were altered.
PostgreSQL still holds 803,761 FIRMS observations. Both original local SQLite
files passed read-only `PRAGMA quick_check`; no scientific volume was deleted.

MODIS Collection 6.1 catalog identities remain `MODIS/061/MOD13Q1` and
`MODIS/061/MCD64A1`. Actual project access, returned image dates, native grid,
raw NDVI/EVI and QA, BurnDate/Uncertainty/QA/FirstDay/LastDay, nodata and HDF
equivalence **could not be tested live**. A catalog listing or controlled fixture
does not prove any of these. The diagnostic deliberately leaves
`hdf_equivalence_verified=false` even if its small future probe passes.

The new-event analysis `event-30c4892d8b3bb714175bb3b2247b7f87` was not
submitted again while registration is absent. Its requested 23.535300201189006 km²
and 2023-10-27 → 2026-10-30 interval are preserved. No new observations,
burned cells, baseline or recovery publication were produced for it in this
follow-up. Available Earth Engine dates and recent gaps remain unverified.

## Tests, browser and deployment

Final suites passed: **174 tests on SQLite (81.66 s)** and **174 tests on
PostgreSQL/PostGIS (31.28 s)**. Tests run against isolated SQLite and
`afterfire_test_ee_setup` PostgreSQL databases, never the archive. The
machine-readable report also records warnings and runtime scope.
Fifteen added cases cover absent/whitespace project settings,
configuration-only behavior, safe SDK error messages, a bounded controlled probe
and first-error termination in the real pipeline. All controlled probe data are
test fixtures and are not stored as NASA publications.

Real browser checks cover Explorer, the persisted publication, Recovery Story,
Before/After, Recovery Intelligence and Reburn headings at desktop 1440 × 1050
and mobile 390 × 844. Repeated saved Analyze preserves job ID and attempt count;
reload preserves the publication. There is no horizontal overflow or JavaScript
page error. These checks verify existing saved science, not a new live analysis.

TypeScript/Vite production compilation passed. A fresh full backend dependency
rebuild was deliberately cancelled as root-disk headroom approached its reserve.
A source-update Docker image was successfully built from the existing backend
image (`sha256:74946d8e3f2680cee1477936671dbe699138fed8e0efa27768a3360721c3dcff`)
with `COPY app /app/app`, then used for both server services. Dependencies were
unchanged. This is not a completed clean dependency rebuild. The root disk later
had more free space; no scientific cache, database or Docker volume was removed
by this work. The frontend source and deployed frontend were unchanged.

Early test attempts were incomplete because the local Python environment lacked
`asyncpg`, a local process was killed, and initial isolated container invocations
omitted pytest configuration, scripts or the boundary fixture. Final isolated
runs include those existing repository inputs. An interrupted PostgreSQL run was
restarted instead of being counted as a pass.

## Delivery and remaining checks

Only the verified setup changes and new verification reports are selected for
Git. Pre-existing untracked reports, screenshots and the Compose backup are
preserved. The clean history starting at `169bf3f` is retained; no filter, reset
or forced push is used. See the delivery commit in Git history and the final
chat response for its SHA and remote verification.

Still required after owner registration: authentication in both services,
collection reads, native raw-band comparison against retained NASA HDFs, the
new-event multiyear analysis, actual acquisition/processing/RAM measurements,
partial-date support, supported recovery/reburn outputs and a second Analyze
that reuses that **new** publication. None is marked complete by software tests.

> **Clean installation activated, 2026-11-06:** Google Cloud CLI 592.0.0 was installed in the user directory from the official archive, SHA-256 `16fda6058d66e4ec29e8575e2b6e19b0d03cea7b091e6730f7e8361209e6955f`. Owner browser login created ADC outside Git, mode 0600; the existing project was retained. The ignored .env path was updated and read-only mounts applied. Backend and worker both passed live MOD13Q1/MCD64A1 native-array probes (6240 decoded bytes, 12 explicit operations each; 13.5565 s and 12.6236 s). No HDF or AppEEARS tasks. Historical HDF equivalence was not rerun because those stores were intentionally removed.

> **New OS, 2026-11-06:** The previous ADC was intentionally removed. Historical live results below do not verify this installation. Follow [clean setup](DOCKER_ENVIRONMENT_RECOVERY.md), preserve the existing Cloud project, and include `compose.clean.yaml` in every command for the new installation. Live science is pending fresh authentication.

# Earth Engine live setup

## Current live follow-up

The owner subsequently supplied a registered project and private ADC. Both
server services now authenticate and retrieve real native arrays. The live
comparison covers all 51 retained reference HDFs with identical raw arrays and
QA masks after the adapter corrections documented in
[live verification](EARTH_ENGINE_LIVE_VERIFICATION.md). The earlier audit below
records the state before registration; it is not the current activation status.

The 2026-10-30 audit found no configured project, Earth Engine user credentials,
or ADC file in either server container or the usual host locations. The owner
confirmed that a project still needs registering. Live activation stops at this
external step; no project, billing account, service account or key was created.

## 1. Register the project (owner action)

Open <https://code.earthengine.google.com/register>, select or create your actual
Google Cloud project, review eligibility and complete the appropriate registration.
Verify that `earthengine.googleapis.com` is enabled. Record the **Project ID**,
not its display name or project number. Do not enter a made-up ID in the config.
Do not activate billing or choose paid access merely to bypass a registration error.

The identity running AfterFire needs Earth Engine Resource Viewer
(`roles/earthengine.viewer`) and Service Usage Consumer
(`roles/serviceusage.serviceUsageConsumer`) permissions on the chosen project.
No Owner/Editor role or asset-write permission is needed for public collection
reads. Organization policies or eligibility may still prevent access.

Official instructions: [project access](https://developers.google.com/earth-engine/guides/access),
[IAM](https://developers.google.com/earth-engine/guides/access_control).

## 2. Authenticate privately

For local development use official Google Application Default Credentials (ADC).
The Google Cloud CLI was not installed on the audited host. Once installed using
[Google's instructions](https://cloud.google.com/sdk/docs/install), run locally:

```sh
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_REGISTERED_PROJECT_ID
```

Complete Google's browser sign-in yourself. Never paste tokens, client secrets
or JSON keys into chat, Git, logs or the frontend. The ADC file normally lives at
`~/.config/gcloud/application_default_credentials.json`; keep it outside this repo
with private file permissions. This file includes a refresh credential, even
though it is not a service-account key.

For production prefer a managed runtime identity or workload identity federation
with ADC. Grant only the permissions above and configure credentials in that
runtime; the file overlay below is unnecessary when managed ADC is available.
Do not generate permanent service-account keys by default.
[Official authentication](https://developers.google.com/earth-engine/guides/auth).

## 3. Configure backend and worker together

In the ignored root `.env`, preserve all other values and set:

```dotenv
AFTERFIRE_API_FIRST=true
AFTERFIRE_SATELLITE_PROVIDER=earth_engine
AFTERFIRE_EARTH_ENGINE_ENABLED=true
AFTERFIRE_EE_PROJECT_ID=YOUR_REGISTERED_PROJECT_ID
AFTERFIRE_APPEEARS_SUBMISSION_ENABLED=false
AFTERFIRE_FULL_HDF_AUTO_DOWNLOAD=false
AFTERFIRE_GOOGLE_CREDENTIALS_FILE=/absolute/private/path/application_default_credentials.json
```

Replace both placeholders with your actual values. `compose.earth-engine.yaml`
is an opt-in overlay: it mounts that existing file read-only as a Compose secret
and sets `GOOGLE_APPLICATION_CREDENTIALS` in **backend and worker only**.
Compose file secrets are local mounts, not an encrypted secret manager. External
identity configurations may require additional runtime mounts or identity access.

```sh
docker compose -f compose.yaml -f compose.earth-engine.yaml config --quiet
docker compose -f compose.yaml -f compose.earth-engine.yaml up -d --build backend analysis-worker
docker compose -f compose.yaml -f compose.earth-engine.yaml exec -T backend python -m app.providers.earth_engine_check --live
docker compose -f compose.yaml -f compose.earth-engine.yaml exec -T analysis-worker python -m app.providers.earth_engine_check --live
```

Use the same two `-f` arguments for later recreations; plain Compose would omit
the secret. Do not use `down -v`. There is no credential mount on the frontend.
Managed identities can use plain `compose.yaml` with appropriate runtime identity
configuration instead. No service/API/billing is enabled by these commands.

## 4. Interpret the probe honestly

Without `--live`, the command checks settings only and never authenticates.
With `--live`, it initializes the real SDK, discovers at most three actual images
per product in July–August 2021, verifies required bands and requests a tiny native
window around 15°E, 37°N through the existing adapter. Image acquisition dates,
band metadata, affine transform, cells, decoded array bytes and elapsed time are
printed as JSON. It does not write a scientific publication or source cache.
Exit 2 means blocked/failed; only `live_probe_passed` confirms this bounded probe.

The operation count covers explicit collection/projection/computePixels calls;
SDK initialization, authentication traffic and retries are excluded. NumPy byte
counts describe received decoded arrays, not HTTP body/wire bytes. A passed probe
does not establish HDF equivalence, sufficient baseline support or successful
multiyear analysis. No mock is used by the probe command.

Initialize the SDK before setting its deadline/retry policy: current releases
require an existing request session. Adapter cache schema 2 restores the native
HDF zero uncertainty only for observed, QA-mapped unburned MCD64A1 cells where
Earth Engine masks that band. Burned/unknown missing uncertainty remains
invalid. Earlier cache schemas are retained but not reused.

For denied/unregistered projects verify registration, API and IAM in Google's
console. For missing credentials check both runtime identities and the mount.
For quota errors stop and retry later within the project's quota; do not add
accounts. The adapter sets a 30 s request deadline and one SDK retry. Global
request/pixel/response/time limits and existing worker concurrency remain active.
Authentication/quota/timeout failures stop acquisition at the first failed
granule; completed source caches and existing checkpoints remain available.

## 5. Finish the scientific activation after registration

Compare identical reference dates against the **retained local** NASA HDFs,
including raw bands, QA, fill, native affine/grid, cell centers and final masks.
Do not download fresh full HDFs for this check. Preserve the reference result SHA
`351b026453f1912204b29822bba6d1fed0c4ac1628432c7701a135563edb7d00`.

The bounded read-only comparator can be rerun using the existing HDF cache:

```sh
docker compose -f compose.yaml -f compose.earth-engine.yaml cp scripts/verify_earth_engine_equivalence.py backend:/tmp/verify_earth_engine_equivalence.py
docker compose -f compose.yaml -f compose.earth-engine.yaml exec -T -e PYTHONPATH=/app backend python /tmp/verify_earth_engine_equivalence.py
```

It writes only `/tmp/afterfire-earth-engine-equivalence.json` in that container,
prints measured results and exits nonzero if AOI values or QA masks differ.

Then Analyze `event-30c4892d8b3bb714175bb3b2247b7f87`, retain missing-date
warnings, verify publication, recovery/reburn support, desktop/mobile and the
second Analyze cache hit. Measure actual acquisition and processing separately.
Until those checks pass, activation remains incomplete. Neither a configured
project nor the historical 1.71 MiB estimate is evidence of real acquisition.


## Release verification — 2026-11-06

See [the current release record](FINAL_RELEASE_VERIFICATION.md) for newly executed multi-continent FIRMS/Earth Engine checks, strict QA and baseline evidence, cold/warm/cache measurements, 189 tests on each database, frontend verification and explicit remaining limits. Earlier measurements in this document remain historical; they were not newly revalidated against deleted HDF sources.

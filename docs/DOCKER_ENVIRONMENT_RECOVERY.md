> **Verified follow-up, 2026-11-06:** The clean installation is running: four services, PostGIS 3.3, 22 public-schema tables. Both backend and worker passed real Earth Engine probes after private browser ADC login; FIRMS is connected. A new real Rhodes candidate produced persisted science and reused its cache. See [current verification](PHASE7_REAL_VERIFICATION.md). Earlier blocked-state notes below are historical.

# Clean API-first environment recovery — 2026-11-06

Status: Phase 0 incomplete. Do not pass the Phase 6.5/7 live-verification gates.

## Superseding owner decision

The owner intentionally deleted the former PostgreSQL archive and scientific cache. Recovery of these stores is no longer requested. Do not search backups or reimport the Italian archive. A new empty PostgreSQL/PostGIS installation is authorized. The earlier audit below is retained as historical evidence only; its backup-recovery requirement is superseded.

## New installation

Use `compose.yaml` plus `compose.clean.yaml`. The project is `afterfire-clean`; explicit volumes are `afterfire-clean-pgdata` and `afterfire-clean-cache`. Never alias them to legacy volumes. The startup script lists volumes before creation and reuses the dedicated installation on subsequent runs. No prune/down-volume command is used.

```sh
sudo bash scripts/start_clean_environment.sh
```

The database has no host port; API and frontend bind only 127.0.0.1:8000 and 127.0.0.1:3000. Schema creation and existing additive migrations run through `init_db`, serialized with the existing PostgreSQL advisory lock. Metadata is seeded, but DEMO_MODE=false prevents demo observations. There is no archive-import command in startup. No new migration framework or second queue is introduced.

The Explorer starts over Italy with on-demand FIRMS and the last seven UTC calendar days. Explicit archive URLs remain supported. An empty optional archive does not prevent global candidates being fetched and selected. Only selected candidates are persisted. NASA provider availability determines which dates are supported; no completeness claim follows from an empty response.

Cache budget is 2 GiB and result budget 1 GiB, using the existing application policy, not filesystem hard quotas. These budgets do not promise deletion of published referenced assets or a bound on PostgreSQL size. Global response cache retains its existing bounded namespace. Existing frontend multistage build is preserved; build contexts exclude satellite raster datasets, database dumps and private files. Backend dependency slimming remains unmeasured and is not claimed.

## Credentials and validation

FIRMS key in ignored .env was validated with the official data-availability endpoint on 2026-11-06: connected, 12 products. No hotspot or scientific analysis has yet been acquired in the new installation. Google ADC is absent and gcloud is not installed. Install the Google Cloud CLI using Google's official Linux archive instructions, then run in the owner's terminal:

```sh
gcloud auth application-default login
gcloud auth application-default set-quota-project ivory-granite-441814-q0
chmod 600 "$HOME/.config/gcloud/application_default_credentials.json"
```

Use the existing registered project. Set AFTERFIRE_GOOGLE_CREDENTIALS_FILE in the ignored .env to the absolute ADC path, then:

```sh
sudo bash scripts/start_clean_environment.sh --earth-engine
sudo docker compose -f compose.yaml -f compose.clean.yaml -f compose.earth-engine.yaml exec -T backend python -m app.providers.earth_engine_check --live
sudo docker compose -f compose.yaml -f compose.clean.yaml -f compose.earth-engine.yaml exec -T analysis-worker python -m app.providers.earth_engine_check --live
```

Both server services receive the existing read-only secret mount. Without the credential overlay, infrastructure can start but Earth Engine science is unavailable. Never interpret that state as live scientific success.

Official references: [CLI installation](https://docs.cloud.google.com/sdk/docs/install-sdk), [Earth Engine authentication](https://developers.google.com/earth-engine/guides/auth).

The agent cannot access the rootful Docker socket and sudo is interactive. The owner chose to execute prepared sudo commands. Runtime schema, service health, image/volume sizes, live science and benchmarks remain pending until those commands succeed. GitHub login was completed by the owner and verified via gh (keyring, HTTPS).

## Earlier audit (superseded recovery policy)

## Observed environment

- Omarchy 4.0.6 (Arch derivative), x86_64, kernel 7.2.8-9-omarchy; pacman installed.
- Docker 29.9.2, Compose plugin 5.6.1, Buildx 0.38.1, containerd 2.4.2 already installed. No reinstallation needed.
- systemctl reports docker inactive in the agent environment. The owner subsequently ran `sudo docker volume ls`: the daemon responded with an empty volume inventory.
- The agent still cannot access the Docker socket; noninteractive sudo requires a password. No docker-group membership or socket permissions were changed.
- Working tree located at `afterfire/` under the supplied workspace. Its physical mount is `/mnt/DATA/Computer Science/nasa/afterfire`.
- The ignored .env exists. API-first and Earth Engine are enabled; satellite provider is earth_engine; AppEEARS submission and full-HDF automatic downloads are disabled.
- The configured external ADC file is absent. The existing project setting was preserved.
- No old PostgreSQL/cache volumes have been recovered. Bounded searches under /mnt/DATA and the user home found no PG_VERSION, .dump, .sql.gz, AfterFire tar archive, or application_default_credentials.json within the searched depths. This does not exclude other disks, deeper directories, or external backups.
- An existing afterfire.db file is preserved. Its presence is not evidence that the original PostgreSQL archive was recovered.
- Approximately 554 GiB free on the project filesystem.
- Copied backend virtualenv executables and frontend .bin entries are regular data files rather than usable Linux executables/symlinks. System Python has none of pytest, FastAPI, SQLAlchemy, NumPy or Earth Engine installed. Rebuild dependencies in an isolated runtime after storage recovery.

## Preservation and checkpoint

The 19 changed/new source files passed working-file secret scanning before staging, staged scanning and git diff whitespace checks. Checkpoint ca7e119 preserves existing global-expansion work without asserting it is verified. Historical screenshots, scientific reports, .env, databases and cache were not added. The commit uses the previous repository author identity for this invocation only; global Git configuration was not changed.

GitHub remote verification failed because HTTPS authentication is unavailable. No push succeeded, no force operation was attempted, and no history was rewritten.

## Verification performed for the clean configuration

Compose validates with the clean overlay. Its resolved project, volumes, loopback ports and DEMO_MODE=false were checked without printing credentials. TypeScript compilation and Vite production build passed. FIRMS availability passed (12 products). All 186 SQLite regressions passed in 22.95 s in the isolated temporary test database, using Python 3.12.15. The sandbox blocked aiosqlite thread notifications even for SELECT 1; the same minimal query and suite passed outside the sandbox. Existing deprecation warnings remain (52,547); no test was changed. PostgreSQL tests, container schema/health, image/volume sizes, browser tests and live Earth Engine science remain pending. Localhost API/frontend were not reachable at the last check.

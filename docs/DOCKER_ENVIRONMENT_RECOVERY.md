# Environment recovery — 2026-11-06

Status: Phase 0 incomplete. Do not pass the Phase 6.5/7 live-verification gates.

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

## Required recovery steps

1. Locate the old Docker data root, PostgreSQL backup and scientific cache on the previous system disk or external backup. Preserve a copy before restoration. Do not run Compose up against empty volumes and label it the original archive.
2. In the owner's terminal, inspect `sudo docker info`, `sudo docker ps -a`, `sudo docker image ls`, `sudo docker system df` and `sudo systemctl status docker`. Avoid sharing full inspect/config output containing environment secrets.
3. Restore the original database and cache using their actual backup format and matching PostgreSQL major version. Validate counts, publications and migration state before application startup. If unavailable, record the archive as missing; use a separately named isolated database only for technical checks.
4. Restore the private ADC outside Git or complete official Google ADC browser authentication for the existing project; update only the ignored .env path. See EARTH_ENGINE_LIVE_SETUP.md. Never paste credentials into chat.
5. Validate `docker compose -f compose.yaml -f compose.earth-engine.yaml config --quiet`. Build/start with those same overlays only after storage and ADC are ready. Existing port bindings must be reviewed before startup to avoid unnecessary public exposure.
6. Run the live Earth Engine check in both backend and worker, validate DB/API/frontend/worker/SSE/cache, then rerun scientific equivalence and comparable live benchmarks.
7. Restore GitHub authentication privately, push main without force and compare the remote SHA with local HEAD.

No services were created, no database initialized, no volume deleted, no NASA task submitted and no satellite data downloaded during this audit. Existing performance documents describe historical measurements, not new measurements on this OS.

References: [Docker installation](https://docs.docker.com/engine/install/), [Arch Docker documentation](https://wiki.archlinux.org/title/Docker).

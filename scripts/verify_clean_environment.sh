#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
compose=(docker compose -f compose.yaml -f compose.clean.yaml)
"${compose[@]}" ps
"${compose[@]}" exec -T db sh -c 'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
SELECT PostGIS_Version();
SELECT count(*) AS schema_tables FROM information_schema.tables WHERE table_schema='public';
SELECT count(*) AS real_or_demo_detections FROM fire_detections;
SELECT count(*) AS candidates FROM fire_event_candidates;
SQL
curl --fail --silent --show-error http://127.0.0.1:8000/api/v1/health
curl --fail --silent --show-error --output /dev/null http://127.0.0.1:3000/
docker system df -v

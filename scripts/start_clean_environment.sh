#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
# Run with sudo from a terminal if the invoking user cannot access Docker.
docker info --format 'Docker {{.ServerVersion}}; root {{.DockerRootDir}}'
docker volume ls
compose=(docker compose -f compose.yaml -f compose.clean.yaml)
if [[ "${1:-}" == "--earth-engine" ]]; then
  compose+=(-f compose.earth-engine.yaml)
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--earth-engine]" >&2; exit 2
fi
"${compose[@]}" config --quiet
# A dedicated Compose project and explicit clean volume names isolate legacy storage.
# Repeated starts reuse this installation; never remove its volumes.
"${compose[@]}" up -d --build --wait --wait-timeout 180
"${compose[@]}" ps
docker system df

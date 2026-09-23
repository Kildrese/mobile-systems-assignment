#!/usr/bin/env bash
# Start the Postgres container and wait until it reports healthy.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TIMEOUT_SECONDS="${DB_UP_TIMEOUT:-60}"

if ! docker info >/dev/null 2>&1; then
  echo "Error: Docker is not running. Start Docker Desktop (or the Docker daemon) and try again." >&2
  exit 1
fi

docker compose up -d db

echo "Waiting for the database to become healthy (timeout: ${TIMEOUT_SECONDS}s)..."
container_id="$(docker compose ps -q db)"
elapsed=0
until [ "$(docker inspect -f '{{.State.Health.Status}}' "$container_id" 2>/dev/null)" = "healthy" ]; do
  if [ "$elapsed" -ge "$TIMEOUT_SECONDS" ]; then
    echo "Error: database did not become healthy within ${TIMEOUT_SECONDS}s. Check 'docker compose logs db'." >&2
    exit 1
  fi
  sleep 1
  elapsed=$((elapsed + 1))
done

echo "Database is healthy."

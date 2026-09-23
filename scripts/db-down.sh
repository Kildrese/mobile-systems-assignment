#!/usr/bin/env bash
# Stop the Postgres container. Pass --reset to also delete the data volume.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

case "${1:-}" in
  "")
    docker compose down
    echo "Database stopped (data kept)."
    ;;
  --reset)
    docker compose down -v
    echo "Database stopped and data volume removed."
    ;;
  *)
    echo "Usage: $0 [--reset]" >&2
    exit 1
    ;;
esac

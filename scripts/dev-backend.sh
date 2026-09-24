#!/usr/bin/env bash
# Start the FastAPI dev server (auto-reload) at http://localhost:8000.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

exec uv run fastapi dev --port 8000

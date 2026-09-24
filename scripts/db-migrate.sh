#!/usr/bin/env bash
# Apply pending Alembic migrations to the database in backend/.env's
# DATABASE_URL (or DATABASE_URL_UNPOOLED, when set).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

uv run alembic upgrade head

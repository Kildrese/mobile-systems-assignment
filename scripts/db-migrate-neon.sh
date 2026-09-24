#!/usr/bin/env bash
# Apply pending Alembic migrations to the Neon production database.
# Reads DATABASE_URL_UNPOOLED from .env.neon (written by `neon link`), since
# migrations need a direct connection rather than the pooled one.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env.neon ]]; then
  echo ".env.neon is missing. Run \`neon link\` and move the Neon variables into .env.neon." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env.neon
set +a

if [[ -z "${DATABASE_URL_UNPOOLED:-}" ]]; then
  echo "DATABASE_URL_UNPOOLED is not set in .env.neon." >&2
  exit 1
fi

cd backend
DATABASE_URL="$DATABASE_URL_UNPOOLED" DATABASE_URL_UNPOOLED="" uv run alembic upgrade head

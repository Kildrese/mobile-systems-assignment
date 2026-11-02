#!/usr/bin/env bash
# Apply pending Alembic migrations to the Neon production database.
# Reads DATABASE_URL_UNPOOLED from .env.neon (written by `neon link`), since
# migrations need a direct connection rather than the pooled one.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# In a git worktree, .env.neon lives in the main checkout.
ENV_NEON="$ROOT/.env.neon"
[[ -f $ENV_NEON ]] || ENV_NEON="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.env.neon"
if [[ ! -f $ENV_NEON ]]; then
  echo ".env.neon is missing. Run \`neon link\` and move the Neon variables into .env.neon." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_NEON"
set +a

if [[ -z "${DATABASE_URL_UNPOOLED:-}" ]]; then
  echo "DATABASE_URL_UNPOOLED is not set in .env.neon." >&2
  exit 1
fi

cd backend
# Two heads means two branches each added a migration: merge master and re-chain first.
heads=$(DATABASE_URL="$DATABASE_URL_UNPOOLED" uv run --quiet alembic heads | grep -c .)
if [[ $heads -ne 1 ]]; then
  echo "Expected one Alembic head, found $heads. Merge master and fix down_revision first." >&2
  exit 1
fi
DATABASE_URL="$DATABASE_URL_UNPOOLED" DATABASE_URL_UNPOOLED="" uv run alembic upgrade head

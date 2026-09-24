#!/usr/bin/env bash
# Vercel's build command (see vercel.json). Builds the app, then, on
# production deployments only, applies pending migrations to Neon.
#
# Migrating after the build means a failed build never touches the database.
# Previews never migrate, so they can't change the production schema.
set -euo pipefail

npm run build

if [[ "${VERCEL_ENV:-}" == "production" ]]; then
  if [[ -z "${DATABASE_URL_UNPOOLED:-}" ]]; then
    echo "DATABASE_URL_UNPOOLED is not set; can't apply migrations." >&2
    exit 1
  fi
  # Migrations need Neon's direct connection, not the pooled one.
  DATABASE_URL="$DATABASE_URL_UNPOOLED" npm run db:migrate
fi

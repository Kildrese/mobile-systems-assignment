#!/usr/bin/env bash
# Apply pending Drizzle migrations to the database in DATABASE_URL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

npm run db:migrate

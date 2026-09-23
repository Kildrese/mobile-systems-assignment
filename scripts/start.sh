#!/usr/bin/env bash
# Bring up the full local stack: .env, dependencies, database, migrations, dev server.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example."
fi

if [ ! -d node_modules ]; then
  echo "Installing npm dependencies..."
  npm install
fi

"$ROOT/scripts/db-up.sh"
"$ROOT/scripts/db-migrate.sh"
exec "$ROOT/scripts/dev.sh"

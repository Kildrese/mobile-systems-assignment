#!/usr/bin/env bash
# Start the Vite dev server at http://localhost:5173.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/frontend"

exec npm run dev

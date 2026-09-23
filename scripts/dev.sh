#!/usr/bin/env bash
# Start the Next.js dev server at http://localhost:3000.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

npm run dev

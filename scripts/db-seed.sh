#!/usr/bin/env bash
# Create the test account (NYUgrader / Courant2026!) unless it already exists.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

uv run python -m app.seed

#!/usr/bin/env bash
# Run the backend tests (pytest, against a separate `<db>_test` database in the
# local Postgres container) and the frontend tests (Vitest). Pass `backend` or
# `frontend` to run only one; extra arguments go to that test runner.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

target="${1:-all}"
[ $# -gt 0 ] && shift

run_backend() {
  for dir in . backend; do
    [ -f "$dir/.env" ] || cp "$dir/.env.example" "$dir/.env"
  done
  "$ROOT/scripts/db-up.sh"
  (cd backend && uv run pytest "$@")
}

run_frontend() {
  (cd frontend && npm test -- "$@")
}

case "$target" in
  all) run_backend && run_frontend ;;
  backend) run_backend "$@" ;;
  frontend) run_frontend "$@" ;;
  *)
    echo "Usage: $0 [all|backend|frontend] [runner args...]" >&2
    exit 1
    ;;
esac

#!/usr/bin/env bash
# Bring up the full local stack: env files, dependencies, database,
# migrations, the test account, then the backend (http://localhost:8000) and
# the frontend (http://localhost:5173). Ctrl-C stops both servers.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

for dir in . backend frontend; do
  if [ ! -f "$dir/.env" ]; then
    cp "$dir/.env.example" "$dir/.env"
    echo "Created $dir/.env from $dir/.env.example."
  fi
done

command -v uv >/dev/null || { echo "Error: uv is required (https://docs.astral.sh/uv/)." >&2; exit 1; }
command -v npm >/dev/null || { echo "Error: Node.js and npm are required." >&2; exit 1; }

if [ ! -d backend/.venv ]; then
  echo "Installing backend dependencies..."
  (cd backend && uv sync)
fi
if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend dependencies..."
  (cd frontend && npm install)
fi

"$ROOT/scripts/db-up.sh"
"$ROOT/scripts/db-migrate.sh"
"$ROOT/scripts/db-seed.sh"

backend_pid=""
frontend_pid=""
cleanup() {
  trap - INT TERM EXIT
  echo "Stopping the dev servers..."
  kill $backend_pid $frontend_pid 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

"$ROOT/scripts/dev-backend.sh" &
backend_pid=$!
"$ROOT/scripts/dev-frontend.sh" &
frontend_pid=$!

echo "Backend:  http://localhost:8000 (API reference at /docs)"
echo "Frontend: http://localhost:5173 (test account: NYUgrader / Courant2026!)"

# Runs until Ctrl-C or until either server exits; the trap stops the other.
# (A poll rather than `wait -n`, which macOS's bash 3.2 lacks.)
while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do
  sleep 1
done

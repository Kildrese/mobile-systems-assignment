# dev-scripts Specification

## Purpose

Shell scripts to start/stop the database, run migrations, and start the dev server, including a single command for the full local stack.
## Requirements
### Requirement: Scripts work from any directory
All shell scripts in `scripts/` SHALL be executable, use strict bash mode, and resolve the repository root themselves so they behave the same regardless of the current working directory.

#### Scenario: Run from a subdirectory
- **WHEN** a developer runs `../scripts/db-up.sh` from inside a subdirectory of the repo
- **THEN** the script behaves the same as when run from the repository root

### Requirement: Start the database and wait for readiness
`scripts/db-up.sh` SHALL verify Docker is available, start the database container, and exit only once the database is healthy.

#### Scenario: Docker running
- **WHEN** Docker is running and a developer runs `scripts/db-up.sh`
- **THEN** the script exits successfully after the database reports healthy

#### Scenario: Docker not running
- **WHEN** the Docker daemon is not reachable
- **THEN** the script exits with a non-zero status and a message telling the user to start Docker

#### Scenario: Readiness timeout
- **WHEN** the database does not become healthy within the timeout
- **THEN** the script exits with a non-zero status and an error message

### Requirement: Stop or reset the database
`scripts/db-down.sh` SHALL stop the database container while keeping data, and with a `--reset` flag SHALL also delete the data volume.

#### Scenario: Stop keeps data
- **WHEN** a developer runs `scripts/db-down.sh`
- **THEN** the container stops and the data volume remains

#### Scenario: Reset removes data
- **WHEN** a developer runs `scripts/db-down.sh --reset`
- **THEN** the container stops and the data volume is removed

### Requirement: Apply migrations via script
`scripts/db-migrate.sh` SHALL apply all pending Alembic migrations to the database in `backend/.env`'s `DATABASE_URL`.

#### Scenario: Migrate
- **WHEN** the database is running and a developer runs `scripts/db-migrate.sh`
- **THEN** all pending migrations are applied

### Requirement: One command runs the full stack
`scripts/start.sh` SHALL bring up the whole local environment:
1. create `.env`, `backend/.env` and `frontend/.env` from their `.env.example` files if missing
2. install backend dependencies (`uv sync`) and frontend dependencies (`npm install`) if missing
3. start the database and wait for it
4. apply migrations
5. create the test account
6. start the backend and frontend dev servers together

Stopping the script (Ctrl-C) SHALL stop both servers.

#### Scenario: Fresh clone
- **WHEN** a developer on a fresh clone (with Docker, Python 3.12+ with `uv`, and Node.js installed) runs `scripts/start.sh`
- **THEN** the env files are created, dependencies are installed, the database starts, migrations are applied, the test account exists, the frontend is reachable at `http://localhost:5173`, and `GET http://localhost:8000/healthz` returns `{ "status": "ok" }`

#### Scenario: Failure stops the chain
- **WHEN** any step before the servers (e.g. starting the database) fails
- **THEN** the script stops immediately with a non-zero status and starts no server

#### Scenario: Ctrl-C stops both servers
- **WHEN** both servers are running and the developer presses Ctrl-C
- **THEN** neither server process keeps running

### Requirement: Seed the test account
`scripts/db-seed.sh` (running `uv run python -m app.seed` in `backend/`) SHALL create a user with username `NYUgrader` (stored as `nyugrader`) and password `Courant2026!`, with first name `NYU`, last name `Grader` and no email, in the database from `DATABASE_URL`. It SHALL use the same registration code as the API. When the username already exists it SHALL leave the user unchanged and exit successfully.

#### Scenario: First run
- **WHEN** a developer runs `scripts/db-seed.sh` on a migrated database without that user
- **THEN** the user is created and can log in with `{ "username": "NYUgrader", "password": "Courant2026!" }`

#### Scenario: Repeated run
- **WHEN** the user already exists and a developer runs `scripts/db-seed.sh` again
- **THEN** the command exits with status 0 and the user is unchanged

### Requirement: Start the dev servers via scripts
`scripts/dev-backend.sh` SHALL start the FastAPI dev server at `http://localhost:8000`, and `scripts/dev-frontend.sh` SHALL start the Vite dev server at `http://localhost:5173`.

#### Scenario: Backend dev server
- **WHEN** the database is running and migrated and a developer runs `scripts/dev-backend.sh`
- **THEN** `GET http://localhost:8000/healthz` returns `{ "status": "ok" }`

#### Scenario: Frontend dev server
- **WHEN** a developer runs `scripts/dev-frontend.sh`
- **THEN** the app is served at `http://localhost:5173`


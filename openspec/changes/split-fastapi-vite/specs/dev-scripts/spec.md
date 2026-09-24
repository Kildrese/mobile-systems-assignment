## ADDED Requirements

### Requirement: Start the dev servers via scripts
`scripts/dev-backend.sh` SHALL start the FastAPI dev server at `http://localhost:8000`, and `scripts/dev-frontend.sh` SHALL start the Vite dev server at `http://localhost:5173`.

#### Scenario: Backend dev server
- **WHEN** the database is running and migrated and a developer runs `scripts/dev-backend.sh`
- **THEN** `GET http://localhost:8000/healthz` returns `{ "status": "ok" }`

#### Scenario: Frontend dev server
- **WHEN** a developer runs `scripts/dev-frontend.sh`
- **THEN** the app is served at `http://localhost:5173`

## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: Start the Next.js dev server via script
**Reason**: The Next.js app is removed.
**Migration**: Use `scripts/dev-backend.sh` and `scripts/dev-frontend.sh` (see "Start the dev servers via scripts"), or `scripts/start.sh` for both.

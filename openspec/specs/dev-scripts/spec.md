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
`scripts/db-migrate.sh` SHALL apply all pending Drizzle migrations to the local database.

#### Scenario: Migrate
- **WHEN** the database is running and a developer runs `scripts/db-migrate.sh`
- **THEN** all pending migrations are applied

### Requirement: Start the Next.js dev server via script
`scripts/dev.sh` SHALL start the Next.js development server.

#### Scenario: Dev server
- **WHEN** a developer runs `scripts/dev.sh`
- **THEN** the app is served at `http://localhost:3000`

### Requirement: One command runs the full stack
`scripts/start.sh` SHALL bring up the whole local environment: create `.env` from `.env.example` if missing, install npm dependencies if `node_modules` is missing, start the database and wait for it, apply migrations, create the test account, and start the dev server.

#### Scenario: Fresh clone
- **WHEN** a developer on a fresh clone (with Docker and Node.js installed) runs `scripts/start.sh`
- **THEN** `.env` is created (including the auth variables), dependencies are installed, the database starts, migrations are applied, the test account exists, and the app is reachable at `http://localhost:3000`, with `GET /healthz` returning `{ "status": "ok" }`

#### Scenario: Failure stops the chain
- **WHEN** any step (e.g. starting the database) fails
- **THEN** the script stops immediately with a non-zero status and does not start the dev server

### Requirement: Seed the test account
`npm run db:seed` SHALL create a user with username `NYUgrader` and password `Courant2026!` in the database from `DATABASE_URL`. When a user with that username already exists it SHALL leave it unchanged and exit successfully.

#### Scenario: First run
- **WHEN** a developer runs `npm run db:seed` on a migrated database without that user
- **THEN** the user is created and can log in with `{ "username": "NYUgrader", "password": "Courant2026!" }`

#### Scenario: Repeated run
- **WHEN** the user already exists and a developer runs `npm run db:seed` again
- **THEN** the command exits with status 0 and the user is unchanged

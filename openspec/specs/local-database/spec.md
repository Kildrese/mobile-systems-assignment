# local-database Specification

## Purpose

PostgreSQL running in a Docker container via docker-compose, with persistent data and env-based configuration.

## Requirements

### Requirement: PostgreSQL runs in a Docker container
The project SHALL provide a Docker Compose configuration that runs a PostgreSQL server in a container, reachable from the host on a configurable port.

#### Scenario: Start the database
- **WHEN** a developer runs `docker compose up -d` from the repository root with a valid `.env`
- **THEN** a PostgreSQL container starts and accepts connections on `localhost:${POSTGRES_PORT}`

#### Scenario: Custom port
- **WHEN** `POSTGRES_PORT` in `.env` is set to a non-default value (e.g. `5433`)
- **THEN** the database is reachable on that port on the host

### Requirement: Database configuration comes from environment variables
The container SHALL read the database user, password, database name, and host port from the `.env` file, and the repository SHALL include a committed `.env.example` with working local defaults while `.env` is git-ignored.

#### Scenario: Example env file exists
- **WHEN** a developer clones the repository
- **THEN** `.env.example` is present and contains `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`, and `DATABASE_URL`

#### Scenario: Local env file is not committed
- **WHEN** a developer creates `.env`
- **THEN** git does not track it

### Requirement: Data persists across container restarts
The database data SHALL be stored in a named Docker volume so it survives stopping and restarting the container.

#### Scenario: Restart keeps data
- **WHEN** rows are inserted, the container is stopped, and then started again
- **THEN** the previously inserted rows are still present

### Requirement: Container reports health
The container SHALL define a healthcheck that reports healthy only once PostgreSQL accepts connections.

#### Scenario: Healthcheck turns healthy
- **WHEN** the container has finished initializing
- **THEN** `docker compose ps` reports the database service as healthy

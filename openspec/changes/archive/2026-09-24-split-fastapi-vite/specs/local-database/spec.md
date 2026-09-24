## MODIFIED Requirements

### Requirement: Database configuration comes from environment variables
The container SHALL read the database user, password, database name and host port from the root `.env` file. The repository SHALL include a committed root `.env.example` with working local defaults for these, and a `backend/.env.example` whose `DATABASE_URL` matches them. Both `.env` files SHALL be git-ignored.

#### Scenario: Example env files exist
- **WHEN** a developer clones the repository
- **THEN** the root `.env.example` contains `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` and `POSTGRES_PORT`, and `backend/.env.example` contains a `DATABASE_URL` pointing at that database

#### Scenario: Local env files are not committed
- **WHEN** a developer creates `.env` or `backend/.env`
- **THEN** git does not track them

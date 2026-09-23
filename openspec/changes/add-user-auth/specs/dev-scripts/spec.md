## MODIFIED Requirements

### Requirement: One command runs the full stack
`scripts/start.sh` SHALL bring up the whole local environment: create `.env` from `.env.example` if missing, install npm dependencies if `node_modules` is missing, start the database and wait for it, apply migrations, and start the dev server.

#### Scenario: Fresh clone
- **WHEN** a developer on a fresh clone (with Docker and Node.js installed) runs `scripts/start.sh`
- **THEN** `.env` is created (including the auth variables), dependencies are installed, the database starts, migrations are applied, and the app is reachable at `http://localhost:3000`, with `GET /healthz` returning `{ "status": "ok" }`

#### Scenario: Failure stops the chain
- **WHEN** any step (e.g. starting the database) fails
- **THEN** the script stops immediately with a non-zero status and does not start the dev server

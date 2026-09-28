## MODIFIED Requirements

### Requirement: Seed the test account
`scripts/db-seed.sh` (running `uv run python -m app.seed` in `backend/`) SHALL create a user with username `NYUgrader` (stored as `nyugrader`) and password `Courant2026!`, with first name `NYU` and last name `Grader`, in the database from `DATABASE_URL`. It SHALL use the same registration code as the API. When the username already exists it SHALL leave the user unchanged and exit successfully.

#### Scenario: First run
- **WHEN** a developer runs `scripts/db-seed.sh` on a migrated database without that user
- **THEN** the user is created and can log in with `{ "username": "NYUgrader", "password": "Courant2026!" }`

#### Scenario: Repeated run
- **WHEN** the user already exists and a developer runs `scripts/db-seed.sh` again
- **THEN** the command exits with status 0 and the user is unchanged

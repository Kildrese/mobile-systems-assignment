## ADDED Requirements

### Requirement: Pydantic models are the source of truth
Every API endpoint SHALL be a FastAPI route that declares:
- its request body and parameters as Pydantic models
- its success response as a `response_model`
- every error status it can return in `responses`, using the shared error model

The same models SHALL validate requests, filter responses (fields not in the response model are never serialized), and generate the OpenAPI document. JSON field names SHALL be camelCase (e.g. `firstName`, `createdAt`), matching the existing API. Request models SHALL ignore unknown keys.

#### Scenario: Response model strips extra fields
- **WHEN** a route returns an ORM object that has fields beyond its response model
- **THEN** the response body contains only the fields declared in the model

#### Scenario: Document builds without a database
- **WHEN** the OpenAPI document is generated with no database running
- **THEN** it is produced without error

## MODIFIED Requirements

### Requirement: Interactive API reference
The backend SHALL serve an interactive API reference (Swagger UI) at `GET /docs`, rendered from `/api/openapi.json`, from which requests can be sent with a bearer token.

#### Scenario: Docs page loads
- **WHEN** a developer opens `http://localhost:8000/docs`
- **THEN** an API reference page listing all documented endpoints is shown, with an "Authorize" control for the bearer token

### Requirement: Committed spec file and generation scripts
The repository SHALL contain `openapi/openapi.json`, generated from the FastAPI app. `uv run python -m app.openapi` in `backend/` SHALL rewrite that file without needing a running server or database. The output SHALL be deterministic: pretty-printed with a trailing newline, and identical across runs for the same code. `uv run python -m app.openapi --check` SHALL exit non-zero with an explanatory message when the committed file differs from what the app generates, and SHALL exit zero otherwise.

#### Scenario: Generate without a database
- **WHEN** the database is stopped and a developer runs `uv run python -m app.openapi` in `backend/`
- **THEN** `openapi/openapi.json` is written and the command exits `0`

#### Scenario: Output is stable
- **WHEN** the generate command runs twice with no code changes
- **THEN** the second run leaves `openapi/openapi.json` byte-for-byte unchanged

#### Scenario: Served and committed documents match
- **WHEN** the committed file is up to date
- **THEN** its contents are equal to the JSON served at `/api/openapi.json`

#### Scenario: Check detects drift
- **WHEN** a Pydantic model or route is changed and the check command runs before regenerating
- **THEN** it exits non-zero and says the spec is out of date and how to regenerate it

#### Scenario: Check passes when in sync
- **WHEN** the committed file matches the app and the check command runs
- **THEN** it exits `0`

## REMOVED Requirements

### Requirement: Zod contracts are the source of truth
**Reason**: The backend is rewritten in Python with FastAPI. Pydantic models take over the role of the Zod contracts.
**Migration**: See "Pydantic models are the source of truth". The frontend gets its types from the generated client (see `frontend-app`) instead of importing the contracts.

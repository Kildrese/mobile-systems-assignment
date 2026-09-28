# api-docs Specification

## Purpose
An OpenAPI 3.1 document generated from the Zod API contracts, served at `/api/openapi.json` with an interactive reference at `/docs`, and a committed `openapi/openapi.json` kept in sync by the `openapi:generate`/`openapi:check` scripts.
## Requirements
### Requirement: OpenAPI document endpoint
The application SHALL serve an OpenAPI 3.1 document at `GET /api/openapi.json` without authentication. The document SHALL include every endpoint of `health-check`, `user-auth` and `user-management`, with request schemas, a response schema for every status code the endpoint can return, and a `bearerAuth` HTTP bearer security scheme applied to every protected endpoint.

#### Scenario: Document is served
- **WHEN** a client sends `GET /api/openapi.json`
- **THEN** the response is `200` with a JSON body whose `openapi` field starts with `3.1`

#### Scenario: All endpoints documented
- **WHEN** the document is inspected
- **THEN** it contains `GET /healthz`, `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`, `POST /api/auth/change-password`, and `GET`, `PATCH` and `DELETE` on `/api/users/{id}`, and it does not contain `/api/auth/change-email`

#### Scenario: Protected endpoints declare bearer auth
- **WHEN** the document is inspected
- **THEN** `/api/auth/me`, `/api/auth/logout`, `/api/auth/change-password` and every `/api/users/{id}` operation list `bearerAuth` under `security`, and each of them documents a `401` response

#### Scenario: Password-confirming endpoint documents 403
- **WHEN** the document is inspected
- **THEN** `/api/auth/change-password` documents a `403` response, and the `ErrorCode` schema includes `INVALID_PASSWORD` and not `EMAIL_TAKEN`

#### Scenario: User schema has no hash and no email
- **WHEN** the `User` component schema in the document is inspected
- **THEN** its properties are exactly `id`, `username`, `firstName`, `lastName`, `createdAt`, `updatedAt`

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

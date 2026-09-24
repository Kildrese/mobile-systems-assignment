# backend-service Specification

## Purpose
TBD - created by archiving change split-fastapi-vite. Update Purpose after archive.
## Requirements
### Requirement: FastAPI service runs locally with uv
The repository SHALL contain a FastAPI application in `backend/`, written in Python 3.12+ and managed with `uv`. It SHALL run on the host without a container. From `backend/`, `uv sync` SHALL install its dependencies from the committed lockfile, and `uv run fastapi dev` SHALL serve it at `http://localhost:8000` with auto-reload.

#### Scenario: Start the backend
- **WHEN** a developer with Python 3.12+ and `uv` installed runs `uv sync` and then `uv run fastapi dev` in `backend/`
- **THEN** `GET http://localhost:8000/healthz` returns `200` with `{ "status": "ok" }`

#### Scenario: Lint and type check pass
- **WHEN** a developer runs `uv run ruff check` and `uv run ruff format --check` in `backend/`
- **THEN** both complete without errors

### Requirement: Configuration from environment variables
The backend SHALL read its configuration from environment variables, loading `backend/.env` when present:
- `DATABASE_URL` (required)
- `CORS_ORIGINS`: a comma-separated list of allowed frontend origins
- `SESSION_TTL_DAYS`: optional, default `7`

`backend/.env.example` SHALL list every variable with working local defaults, and `backend/.env` SHALL be git-ignored. A missing `DATABASE_URL` SHALL stop the service at startup with a message naming the variable.

#### Scenario: Missing DATABASE_URL
- **WHEN** the backend starts with `DATABASE_URL` unset
- **THEN** it exits with an error message stating that `DATABASE_URL` is missing

#### Scenario: Example env file exists
- **WHEN** a developer clones the repository
- **THEN** `backend/.env.example` is present and contains `DATABASE_URL` and `CORS_ORIGINS`

### Requirement: Database connection
The backend SHALL connect to PostgreSQL with SQLAlchemy 2 using the psycopg 3 driver and one connection pool per process. It SHALL work with Neon's pooled endpoint, so server-side prepared statements SHALL be disabled.

#### Scenario: Queries through the pool
- **WHEN** the backend serves several authenticated requests in a row
- **THEN** each is answered from the pool without opening a new connection per request

### Requirement: CORS allow-list
The backend SHALL answer cross-origin requests only for origins listed in `CORS_ORIGINS`. For those origins it SHALL:
- answer preflight (`OPTIONS`) requests for the API's methods (`GET`, `POST`, `PATCH`, `DELETE`) and the `Authorization` and `Content-Type` request headers
- include `Access-Control-Allow-Origin` with that origin on responses, errors included

It SHALL NOT send `Access-Control-Allow-Credentials`, since the API uses bearer tokens and no cookies. Requests from other origins SHALL get no CORS headers. Requests without an `Origin` header (e.g. curl) SHALL be served normally.

#### Scenario: Allowed origin preflight
- **WHEN** a browser at `http://localhost:5173` (listed in `CORS_ORIGINS`) sends `OPTIONS /api/auth/me` with `Access-Control-Request-Method: GET` and `Access-Control-Request-Headers: authorization`
- **THEN** the response is `200` with `Access-Control-Allow-Origin: http://localhost:5173` and allows the `authorization` header

#### Scenario: Unknown origin
- **WHEN** a request carries `Origin: https://evil.example`, which is not listed
- **THEN** the response has no `Access-Control-Allow-Origin` header

#### Scenario: Error responses carry CORS headers
- **WHEN** an allowed origin calls `GET /api/auth/me` without a token
- **THEN** the `401` response includes `Access-Control-Allow-Origin` for that origin, so the browser can read the error

#### Scenario: No credentials mode
- **WHEN** an allowed origin sends a preflight
- **THEN** the response does not include `Access-Control-Allow-Credentials`

### Requirement: Uniform error responses
Every error the backend returns SHALL use the API's error shape `{ "error": { "code", "message", "details"? } }`:
- **Invalid JSON, or a body or parameters failing validation:** FastAPI's default `422` SHALL be replaced by `400` with code `VALIDATION_ERROR`. `details` SHALL hold only each issue's path, code and message, never the submitted value.
- **Unknown routes:** `404` with code `NOT_FOUND`.
- **Unsupported methods:** `405`, in the same shape.
- **Unhandled exceptions:** `500` with code `INTERNAL`. They SHALL be logged without the request body.

#### Scenario: Validation error shape
- **WHEN** a client posts `{"password": "short"}` to `/api/auth/register`
- **THEN** the response is `400` with `error.code` equal to `VALIDATION_ERROR`, and `error.details` lists paths and messages without the value `short`

#### Scenario: Malformed JSON
- **WHEN** a client posts the body `{not json` to `/api/auth/login`
- **THEN** the response is `400` with `error.code` equal to `VALIDATION_ERROR`

#### Scenario: Unknown route
- **WHEN** a client requests `GET /api/nope`
- **THEN** the response is `404` with the error shape


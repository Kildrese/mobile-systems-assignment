# api-docs Specification

## Purpose
An OpenAPI 3.1 document generated from the Zod API contracts, served at `/api/openapi.json` with an interactive reference at `/docs`, and a committed `openapi/openapi.json` kept in sync by the `openapi:generate`/`openapi:check` scripts.

## Requirements
### Requirement: Zod contracts are the source of truth
Every API endpoint SHALL be described by one Zod contract (method, path, auth, params, body, and a response schema per status code). The same contract SHALL be used to validate requests, to shape responses, and to generate the OpenAPI document. The contract and document-builder modules SHALL NOT import the database, the auth instance, or Next.js runtime modules.

#### Scenario: Response schema strips extra fields
- **WHEN** a handler returns an object with fields beyond its response schema
- **THEN** the response body contains only the fields declared in the schema

#### Scenario: Contracts load without runtime dependencies
- **WHEN** the contracts module is imported with no `DATABASE_URL` or `BETTER_AUTH_SECRET` set
- **THEN** it loads without error

### Requirement: OpenAPI document endpoint
The application SHALL serve an OpenAPI 3.1 document at `GET /api/openapi.json` without authentication. The document SHALL include every endpoint of `health-check`, `user-auth` and `user-management`, with request schemas, a response schema for every status code the endpoint can return, and a `bearerAuth` HTTP bearer security scheme applied to every protected endpoint.

#### Scenario: Document is served
- **WHEN** a client sends `GET /api/openapi.json`
- **THEN** the response is `200` with a JSON body whose `openapi` field starts with `3.1`

#### Scenario: All endpoints documented
- **WHEN** the document is inspected
- **THEN** it contains `GET /healthz`, `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`, and `GET`, `PATCH` and `DELETE` on `/api/users/{id}`

#### Scenario: Protected endpoints declare bearer auth
- **WHEN** the document is inspected
- **THEN** `/api/auth/me` and every `/api/users/{id}` operation list `bearerAuth` under `security`, and each of them documents a `401` response

#### Scenario: User schema has no hash
- **WHEN** the `User` component schema in the document is inspected
- **THEN** its properties are exactly `id`, `email`, `firstName`, `lastName`, `createdAt`, `updatedAt`

### Requirement: Interactive API reference
The application SHALL serve an interactive API reference at `GET /docs`, rendered from `/api/openapi.json`, from which requests can be sent with a bearer token.

#### Scenario: Docs page loads
- **WHEN** a developer opens `http://localhost:3000/docs`
- **THEN** an API reference page listing all documented endpoints is shown

### Requirement: Committed spec file and generation scripts
The repository SHALL contain `openapi/openapi.json`, generated from the contracts. `npm run openapi:generate` SHALL rewrite that file without needing a running server or database. The output SHALL be deterministic: pretty-printed with a trailing newline, and identical across runs for the same contracts. `npm run openapi:check` SHALL exit non-zero with an explanatory message when the committed file differs from what the contracts generate, and SHALL exit zero otherwise.

#### Scenario: Generate without a database
- **WHEN** the database is stopped and a developer runs `npm run openapi:generate`
- **THEN** `openapi/openapi.json` is written and the command exits `0`

#### Scenario: Output is stable
- **WHEN** `npm run openapi:generate` runs twice with no contract changes
- **THEN** the second run leaves `openapi/openapi.json` byte-for-byte unchanged

#### Scenario: Served and committed documents match
- **WHEN** the committed file is up to date
- **THEN** its contents are equal to the JSON served at `/api/openapi.json`

#### Scenario: Check detects drift
- **WHEN** a contract is changed and `npm run openapi:check` runs before regenerating
- **THEN** it exits non-zero and says the spec is out of date and to run `npm run openapi:generate`

#### Scenario: Check passes when in sync
- **WHEN** the committed file matches the contracts and `npm run openapi:check` runs
- **THEN** it exits `0`


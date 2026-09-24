## MODIFIED Requirements

### Requirement: OpenAPI document endpoint
The application SHALL serve an OpenAPI 3.1 document at `GET /api/openapi.json` without authentication. The document SHALL include every endpoint of `health-check`, `user-auth` and `user-management`, with request schemas, a response schema for every status code the endpoint can return, and a `bearerAuth` HTTP bearer security scheme applied to every protected endpoint.

#### Scenario: Document is served
- **WHEN** a client sends `GET /api/openapi.json`
- **THEN** the response is `200` with a JSON body whose `openapi` field starts with `3.1`

#### Scenario: All endpoints documented
- **WHEN** the document is inspected
- **THEN** it contains `GET /healthz`, `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`, `POST /api/auth/change-password`, `POST /api/auth/change-email`, and `GET`, `PATCH` and `DELETE` on `/api/users/{id}`

#### Scenario: Protected endpoints declare bearer auth
- **WHEN** the document is inspected
- **THEN** `/api/auth/me`, `/api/auth/logout`, `/api/auth/change-password`, `/api/auth/change-email` and every `/api/users/{id}` operation list `bearerAuth` under `security`, and each of them documents a `401` response

#### Scenario: Password-confirming endpoints document 403
- **WHEN** the document is inspected
- **THEN** `/api/auth/change-password` and `/api/auth/change-email` each document a `403` response, and the `ErrorCode` schema includes `INVALID_PASSWORD`

#### Scenario: User schema has no hash
- **WHEN** the `User` component schema in the document is inspected
- **THEN** its properties are exactly `id`, `email`, `firstName`, `lastName`, `createdAt`, `updatedAt`

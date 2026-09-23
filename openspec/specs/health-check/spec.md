# health-check Specification

## Purpose
An unauthenticated liveness endpoint at `/healthz` that reports whether the process is serving requests, independent of the database.

## Requirements
### Requirement: Liveness endpoint
The application SHALL expose `GET /healthz` without authentication, and it SHALL respond `200` with the JSON body `{ "status": "ok" }`. The endpoint SHALL NOT depend on the database, so it reports whether the process is serving requests.

#### Scenario: Health check succeeds
- **WHEN** a client sends `GET /healthz` with no `Authorization` header
- **THEN** the response status is `200`, the `Content-Type` is JSON, and the body is exactly `{ "status": "ok" }`

#### Scenario: Health check ignores credentials
- **WHEN** a client sends `GET /healthz` with an invalid `Authorization: Bearer` header
- **THEN** the response is still `200` with `{ "status": "ok" }`

#### Scenario: Health check without database
- **WHEN** the database is stopped and a client sends `GET /healthz`
- **THEN** the response is `200` with `{ "status": "ok" }`


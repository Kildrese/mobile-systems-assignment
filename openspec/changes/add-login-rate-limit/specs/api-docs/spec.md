## ADDED Requirements

### Requirement: Login documents rate limiting
The OpenAPI document SHALL list a `429` response with the `Error` schema and a `Retry-After` header on `POST /api/auth/login`, and the `ErrorCode` schema SHALL include `RATE_LIMITED`.

#### Scenario: 429 on login
- **WHEN** the served OpenAPI document is inspected
- **THEN** `POST /api/auth/login` documents a `429` response, and `ErrorCode` includes `RATE_LIMITED`

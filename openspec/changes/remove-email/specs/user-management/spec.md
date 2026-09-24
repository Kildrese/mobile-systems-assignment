## MODIFIED Requirements

### Requirement: Update own user
`PATCH /api/users/:id` SHALL accept a JSON body with optional `username` (same rules as at registration) and optional `firstName` (non-empty) and `lastName` (may be empty). It SHALL require at least one of them; other keys SHALL be ignored, so a body with only other keys (such as `email`, `password` or `id`) SHALL be rejected with `400`. If the username is taken by another user (compared case-insensitively) it SHALL respond `409` with code `USERNAME_TAKEN` and change nothing. On success it SHALL update the fields that were provided, store the username lowercased, update `updatedAt`, and respond `200` with the updated user object. The password SHALL NOT be changeable through this endpoint.

#### Scenario: Update first name
- **WHEN** user A patches `{ "firstName": "Augusta" }` on their own id
- **THEN** the response is `200` with `firstName` equal to `Augusta`, `lastName` unchanged, and `updatedAt` later than before

#### Scenario: Change username
- **WHEN** user A patches `{ "username": "Augusta" }` on their own id
- **THEN** the response is `200` with `username` equal to `augusta`, A can log in with `augusta`, and A's previous username no longer logs in

#### Scenario: Username taken
- **WHEN** user A patches `{ "username": "<B's username>" }` on their own id
- **THEN** the response is `409` with `error.code` equal to `USERNAME_TAKEN` and A's record is unchanged

#### Scenario: Empty body
- **WHEN** user A patches `{}` on their own id
- **THEN** the response is `400` with `error.code` equal to `VALIDATION_ERROR`

#### Scenario: Forbidden fields
- **WHEN** user A patches `{ "email": "new@example.com" }` or `{ "password": "x" }` or `{ "id": "<uuid>" }` on their own id
- **THEN** the response is `400` and the user record is unchanged

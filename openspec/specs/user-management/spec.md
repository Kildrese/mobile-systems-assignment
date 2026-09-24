# user-management Specification

## Purpose
Authenticated read, update and delete of users by id, restricted to the caller's own account; any other id returns `404`.

## Requirements
### Requirement: Users can only access their own account
`GET`, `PATCH` and `DELETE` on `/api/users/:id` SHALL require bearer authentication (see `user-auth`). When `:id` is not the authenticated user's own id, whether it belongs to another user, doesn't exist, or isn't a valid UUID, the endpoint SHALL respond `404` with code `NOT_FOUND`, and the response SHALL be identical in all three cases. The endpoint SHALL NOT read, change or delete any data in that case. The ownership check SHALL happen before any database lookup of `:id`.

#### Scenario: Another user's id
- **WHEN** user A calls `GET`, `PATCH` or `DELETE /api/users/<B's id>` with A's token
- **THEN** each response is `404` with `error.code` equal to `NOT_FOUND`, and B's record is unchanged

#### Scenario: Nonexistent id looks the same
- **WHEN** user A calls `GET /api/users/<random unused UUID>`
- **THEN** the response status and body are identical to requesting another user's id

#### Scenario: Invalid UUID
- **WHEN** user A calls `GET /api/users/not-a-uuid`
- **THEN** the response is `404`, not `400` or `500`

#### Scenario: Unauthenticated access
- **WHEN** a client calls any `/api/users/:id` method with no token or an invalid token
- **THEN** the response is `401`, even if `:id` is valid

### Requirement: Read own user
`GET /api/users/:id` SHALL respond `200` with the user object when `:id` is the caller's own id.

#### Scenario: Read self
- **WHEN** user A calls `GET /api/users/<A's id>` with A's token
- **THEN** the response is `200` with A's user object

### Requirement: Update own user
`PATCH /api/users/:id` SHALL accept a JSON body with optional `username` (same rules as at registration) and optional `firstName` and `lastName` (non-empty strings). It SHALL require at least one of them and SHALL reject any other keys with `400`. If the username is taken by another user (compared case-insensitively) it SHALL respond `409` with code `USERNAME_TAKEN` and change nothing. On success it SHALL update the fields that were provided, store the username lowercased, set `name` to `"<firstName> <lastName>"`, update `updatedAt`, and respond `200` with the updated user object. `email` and `password` SHALL NOT be changeable through this endpoint.

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

### Requirement: Delete own user
`DELETE /api/users/:id` SHALL delete the caller's user record together with their accounts and sessions, and SHALL respond `204` with an empty body. After deletion, the caller's token SHALL no longer authenticate.

#### Scenario: Delete self
- **WHEN** user A calls `DELETE /api/users/<A's id>` with A's token
- **THEN** the response is `204` and A's `user`, `account` and `session` rows no longer exist

#### Scenario: Token invalid after deletion
- **WHEN** user A deletes their account and then calls `GET /api/auth/me` with the same token
- **THEN** the response is `401`

#### Scenario: Cannot log in after deletion
- **WHEN** user A deletes their account and then posts their old credentials to `/api/auth/login`
- **THEN** the response is `401` with `error.code` equal to `INVALID_CREDENTIALS`


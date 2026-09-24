# user-auth Specification

## Purpose
Account registration, login by email or username that returns a bearer token, resolving the current user from that token, and the Better Auth data model (`user`, `account`, `session`, `verification`), under JSON API conventions that never expose password hashes.

## Requirements
### Requirement: User data model
The database SHALL contain the Better Auth tables `user`, `account`, `session` and `verification`, each with a UUID primary key. The `user` table SHALL have `email` (unique, not null), `username` (unique, not null, stored lowercased), `first_name` (not null), `last_name` (not null), `name` (not null, always equal to `first_name + " " + last_name`), and `created_at` and `updated_at` timestamps. Password hashes SHALL be stored only in `account.password` and never on `user`. The `account.user_id` and `session.user_id` columns SHALL reference `user.id` with `ON DELETE CASCADE`.

#### Scenario: Registered user is stored with a UUID
- **WHEN** a user registers successfully
- **THEN** a `user` row exists whose `id` is a UUID and whose `first_name`, `last_name` and `email` match the request, whose `username` is the requested username lowercased, and whose `name` is `"<firstName> <lastName>"`

#### Scenario: Password stored only as a hash on account
- **WHEN** a user registers with password `P`
- **THEN** exactly one `account` row for that user has a non-null `password` value that is not equal to `P`, and the `user` table has no password column

#### Scenario: Deleting a user removes credentials and sessions
- **WHEN** a `user` row is deleted
- **THEN** all `account` and `session` rows referencing that user are deleted too

### Requirement: JSON API conventions
Every endpoint in this capability and in `user-management` SHALL accept JSON request bodies and SHALL return JSON response bodies, errors included. Every non-2xx response SHALL have the shape `{ "error": { "code": string, "message": string, "details"?: any } }`. A request body that is not valid JSON, or that fails schema validation, SHALL return `400` with code `VALIDATION_ERROR`. Unexpected server failures SHALL return `500` with code `INTERNAL` and a generic message, with no error messages, stack traces or request data in the response, in any environment.

#### Scenario: Malformed JSON body
- **WHEN** a client sends `POST /api/auth/login` with body `{not json`
- **THEN** the response is `400` with `error.code` equal to `VALIDATION_ERROR`

#### Scenario: Validation errors do not echo secrets
- **WHEN** a client sends `POST /api/auth/register` with an invalid body that includes a `password` value
- **THEN** the `400` response body does not contain that password value

#### Scenario: Internal errors are opaque
- **WHEN** a handler throws an unexpected error
- **THEN** the response is `500` with `{ "error": { "code": "INTERNAL", "message": "Internal server error" } }` and no stack trace

### Requirement: Password hashes are never returned
No endpoint SHALL ever include a password hash, or any field of the `account` or `session` tables other than the login token, in a response body, whether it succeeds or fails and whatever the environment. User objects in responses SHALL contain exactly these fields: `id`, `email`, `username`, `firstName`, `lastName`, `createdAt`, `updatedAt`.

#### Scenario: User objects expose only allow-listed fields
- **WHEN** any endpoint returns a user object
- **THEN** its keys are exactly `id`, `email`, `username`, `firstName`, `lastName`, `createdAt`, `updatedAt`

#### Scenario: No hash in any response
- **WHEN** every endpoint is called with both valid and invalid input
- **THEN** no response body contains the stored `account.password` value or a key named `password`, `passwordHash` or `hash`

### Requirement: Bearer token authentication
Protected endpoints SHALL authenticate the caller only from an `Authorization: Bearer <token>` header; cookies SHALL be ignored. When the header is missing, is not in the form `Bearer <token>`, or carries a token that is unknown, expired or belongs to a deleted session or user, the endpoint SHALL respond `401` with code `UNAUTHORIZED`. It SHALL never respond `200` or `500` in these cases.

#### Scenario: Missing token
- **WHEN** a client calls `GET /api/auth/me` with no `Authorization` header
- **THEN** the response is `401` with `error.code` equal to `UNAUTHORIZED`

#### Scenario: Malformed header
- **WHEN** a client calls `GET /api/auth/me` with `Authorization: Basic abc`, `Authorization: Bearer` or `Authorization: Bearer    `
- **THEN** each response is `401`

#### Scenario: Garbage token
- **WHEN** a client calls `GET /api/auth/me` with `Authorization: Bearer not-a-real-token`
- **THEN** the response is `401`

#### Scenario: Expired token
- **WHEN** a client calls `GET /api/auth/me` with a token whose session `expires_at` is in the past
- **THEN** the response is `401`

#### Scenario: Token of a deleted user
- **WHEN** a user deletes their account and then calls `GET /api/auth/me` with the same token
- **THEN** the response is `401`

#### Scenario: Cookie alone is not accepted
- **WHEN** a client calls `GET /api/auth/me` with a valid session cookie but no `Authorization` header
- **THEN** the response is `401`

### Requirement: Register an account
`POST /api/auth/register` SHALL NOT require authentication. It SHALL accept `{ email, username, password, firstName, lastName }`, where `email` is a valid email, `username` has 3 to 30 characters that are letters, digits, `_` or `.`, `password` has at least 8 characters, and `firstName` and `lastName` are non-empty strings. Any other keys SHALL be rejected with `400`. On success it SHALL create the user and respond `201` with the user object. It SHALL NOT return a token. If the email is already registered (compared case-insensitively), it SHALL respond `409` with code `EMAIL_TAKEN`. Otherwise, if the username is already taken (compared case-insensitively), it SHALL respond `409` with code `USERNAME_TAKEN`. Usernames SHALL be stored lowercased.

#### Scenario: Successful registration
- **WHEN** a client posts `{ "email": "a@example.com", "username": "Ada_L", "password": "correct-horse", "firstName": "Ada", "lastName": "Lovelace" }`
- **THEN** the response is `201` with a user object whose `email` is `a@example.com`, `username` is `ada_l`, `firstName` is `Ada`, `lastName` is `Lovelace`, and `id` is a UUID, and the body has no `token`

#### Scenario: Duplicate email
- **WHEN** a client registers `A@Example.com` after `a@example.com` already exists
- **THEN** the response is `409` with `error.code` equal to `EMAIL_TAKEN`

#### Scenario: Duplicate username
- **WHEN** a client registers a new email with username `ADA_L` after `ada_l` already exists
- **THEN** the response is `409` with `error.code` equal to `USERNAME_TAKEN`

#### Scenario: Missing or invalid fields
- **WHEN** a client posts a body missing `lastName` or `username`, or with an invalid email, or with a 7-character password, or with a username that is shorter than 3 characters, longer than 30 or contains other characters than letters, digits, `_` and `.`
- **THEN** the response is `400` with `error.code` equal to `VALIDATION_ERROR` and no user is created

#### Scenario: Unknown fields are not stored
- **WHEN** a client posts a valid body that also includes `"id": "<some uuid>"` or `"emailVerified": true`
- **THEN** the response is `400` with `error.code` equal to `VALIDATION_ERROR` and no user is created

### Requirement: Log in
`POST /api/auth/login` SHALL NOT require authentication. It SHALL accept `{ identifier, password }`, where `identifier` is the user's email or username. An `identifier` containing `@` SHALL be treated as an email, anything else as a username; both SHALL be compared case-insensitively. With correct credentials it SHALL create a session and respond `200` with `{ "token": string, "user": User }`, where `token` works as a bearer token on protected endpoints. With an unknown email, an unknown or malformed username, or a wrong password it SHALL respond `401` with code `INVALID_CREDENTIALS`, and all these cases SHALL produce identical response bodies.

#### Scenario: Successful login
- **WHEN** a registered user posts correct credentials
- **THEN** the response is `200` with a non-empty `token` and the user object

#### Scenario: Login with username
- **WHEN** a user registered with username `ada_l` posts `{ "identifier": "ADA_L", "password": <correct> }`
- **THEN** the response is `200` with a non-empty `token` and that user's user object

#### Scenario: Token works on protected routes
- **WHEN** the client calls `GET /api/auth/me` with `Authorization: Bearer <token from login>`
- **THEN** the response is `200`

#### Scenario: Wrong password
- **WHEN** a client posts a registered email with the wrong password
- **THEN** the response is `401` with `error.code` equal to `INVALID_CREDENTIALS`

#### Scenario: Unknown email or username is indistinguishable
- **WHEN** a client posts an unregistered email, an unregistered username, or a malformed username such as `a`
- **THEN** the response status and body are identical to the wrong-password case

#### Scenario: Login does not set cookies
- **WHEN** a login succeeds
- **THEN** the response has no `Set-Cookie` header

### Requirement: Current user
`GET /api/auth/me` SHALL require authentication. It SHALL respond `200` with the authenticated user's user object.

#### Scenario: Returns the logged-in user
- **WHEN** an authenticated user calls `GET /api/auth/me`
- **THEN** the response is `200` with that user's user object, whose `id` matches the user who logged in


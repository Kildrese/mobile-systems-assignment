# user-auth Specification

## Purpose
Account registration, login by email or username that returns a bearer token, resolving the current user from that token, and the Better Auth data model (`user`, `account`, `session`, `verification`), under JSON API conventions that never expose password hashes.
## Requirements
### Requirement: User data model
The database SHALL contain the tables `users`, `user_passwords` and `sessions`, each with a UUID primary key (`user_passwords` uses `user_id` as its key).
- **`users`** SHALL have:
  - `email`: nullable, unique, stored lowercased
  - `username`: unique, not null, stored lowercased
  - `first_name`: not null
  - `last_name`: not null, may be empty
  - `created_at` and `updated_at` timestamps
- **`user_passwords`** SHALL hold the password hash, one row per user.
- **`sessions`** SHALL hold `token_hash` (unique), `user_id`, `expires_at` and timestamps.

Password hashes SHALL be stored only in `user_passwords` and never on `users`. The `user_passwords.user_id` and `sessions.user_id` columns SHALL reference `users.id` with `ON DELETE CASCADE`.

#### Scenario: Registered user is stored with a UUID
- **WHEN** a user registers successfully
- **THEN** a `users` row exists whose `id` is a UUID, whose `first_name`, `last_name` and `email` match the request (the email lowercased), and whose `username` is the requested username lowercased

#### Scenario: User without an email
- **WHEN** a user registers with only a username and a password
- **THEN** their `users.email` is `NULL`, and a second user can also register without an email

#### Scenario: Password stored only as a hash
- **WHEN** a user registers with password `P`
- **THEN** exactly one `user_passwords` row for that user has a hash that is not equal to `P`, and the `users` table has no password column

#### Scenario: Deleting a user removes credentials and sessions
- **WHEN** a `users` row is deleted
- **THEN** all `user_passwords` and `sessions` rows referencing that user are deleted too

### Requirement: JSON API conventions
Every endpoint in this capability and in `user-management` SHALL accept JSON request bodies and SHALL return JSON response bodies, errors included. Every non-2xx response SHALL have the shape `{ "error": { "code": string, "message": string, "details"?: any } }`. A request body that is not valid JSON, or that fails schema validation, SHALL return `400` with code `VALIDATION_ERROR`. Keys a request body doesn't define SHALL be ignored: they SHALL NOT cause an error and SHALL NOT be stored. Unexpected server failures SHALL return `500` with code `INTERNAL` and a generic message, with no error messages, stack traces or request data in the response, in any environment.

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
No endpoint SHALL ever include a password hash, or any field of the `user_passwords` or `sessions` tables other than the login token, in a response body, whether it succeeds or fails and whatever the environment. User objects in responses SHALL contain exactly these fields: `id`, `email`, `username`, `firstName`, `lastName`, `createdAt`, `updatedAt`.

#### Scenario: User objects expose only allow-listed fields
- **WHEN** any endpoint returns a user object
- **THEN** its keys are exactly `id`, `email`, `username`, `firstName`, `lastName`, `createdAt`, `updatedAt`

#### Scenario: No hash in any response
- **WHEN** every endpoint is called with both valid and invalid input
- **THEN** no response body contains a stored `user_passwords` hash, a `sessions.token_hash` value, or a key named `password`, `passwordHash` or `hash`

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
`POST /api/auth/register` SHALL NOT require authentication. It SHALL accept `{ email?, username?, password, firstName?, lastName? }` with at least one of `email` and `username`, where:
- `email` is a valid email of at most 254 characters
- `username` has 3 to 30 characters that are letters, digits, `_` or `.`
- `password` has 8 to 128 characters
- `firstName` is a non-empty string and `lastName` a possibly empty string, each at most 100 characters

Defaults for missing fields:
- Without a username, one SHALL be derived from the email's local part (reduced to allowed characters, at most 21 of them) plus `_` and 8 random hex digits.
- Without an email, the user SHALL be stored with no email and returned with `"email": null`.
- Without `firstName` it SHALL be the username, and without `lastName` it SHALL be empty.

On success it SHALL create the user and respond `201` with the user object. It SHALL NOT return a token. If the email is already registered (compared case-insensitively), it SHALL respond `409` with code `EMAIL_TAKEN`. Otherwise, if the username is already taken (compared case-insensitively), it SHALL respond `409` with code `USERNAME_TAKEN`. Usernames and emails SHALL be stored lowercased.

#### Scenario: Successful registration
- **WHEN** a client posts `{ "email": "a@example.com", "username": "Ada_L", "password": "correct-horse", "firstName": "Ada", "lastName": "Lovelace" }`
- **THEN** the response is `201` with a user object whose `email` is `a@example.com`, `username` is `ada_l`, `firstName` is `Ada`, `lastName` is `Lovelace`, and `id` is a UUID, and the body has no `token`

#### Scenario: Duplicate email
- **WHEN** a client registers `A@Example.com` after `a@example.com` already exists
- **THEN** the response is `409` with `error.code` equal to `EMAIL_TAKEN`

#### Scenario: Duplicate username
- **WHEN** a client registers a new email with username `ADA_L` after `ada_l` already exists
- **THEN** the response is `409` with `error.code` equal to `USERNAME_TAKEN`

#### Scenario: Duplicate username without an email
- **WHEN** a client posts `{ "username": "ADA_L", "password": "correct-horse" }` after `ada_l` already exists
- **THEN** the response is `409` with `error.code` equal to `USERNAME_TAKEN`

#### Scenario: Missing or invalid fields
- **WHEN** a client posts a body missing `password`, or missing both `email` and `username`, or with an invalid email, or with a 7-character password, or with a username that is shorter than 3 characters, longer than 30 or contains other characters than letters, digits, `_` and `.`
- **THEN** the response is `400` with `error.code` equal to `VALIDATION_ERROR` and no user is created

#### Scenario: Unknown fields are not stored
- **WHEN** a client posts a valid body that also includes `"id": "<some uuid>"` and `"emailVerified": true`
- **THEN** the response is `201`, and the user's `id` is not the one sent

#### Scenario: Username and password only
- **WHEN** a client posts `{ "username": "Solo", "password": "correct-horse" }`
- **THEN** the response is `201` with `username` `solo`, `email` `null`, `firstName` `solo` and `lastName` `""`

#### Scenario: Email and password only
- **WHEN** a client posts `{ "email": "a@example.com", "password": "correct-horse" }`
- **THEN** the response is `201` with a username that starts with `a_` followed by 8 hex digits

### Requirement: Log in
`POST /api/auth/login` SHALL NOT require authentication. It SHALL accept `{ identifier, password }`, where `identifier` is the user's email or username. `email` and `username` SHALL be accepted as other names for `identifier`, with the same meaning, so `{ "username": "ada", "password": … }` and `{ "email": "a@example.com", "password": … }` also work. A body with none of the three SHALL be rejected with `400`. An `identifier` containing `@` SHALL be treated as an email, anything else as a username; both SHALL be compared case-insensitively. With correct credentials it SHALL create a session and respond `200` with `{ "token": string, "user": User }`, where `token` works as a bearer token on protected endpoints. With an unknown email, an unknown or malformed username, or a wrong password it SHALL respond `401` with code `INVALID_CREDENTIALS`, and all these cases SHALL produce identical response bodies.

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

### Requirement: Log out
`POST /api/auth/logout` SHALL require bearer authentication and take no request body. It SHALL revoke the session belonging to the presented token and respond `204` with no body. Other sessions of the same user SHALL stay valid.

#### Scenario: Token stops working after logout
- **WHEN** a client calls `POST /api/auth/logout` with a valid token and then calls `GET /api/auth/me` with the same token
- **THEN** the logout response is `204` and the `/me` response is `401`

#### Scenario: Other sessions survive
- **WHEN** a user has logged in twice (tokens `T1` and `T2`) and logs out with `T1`
- **THEN** `GET /api/auth/me` with `T2` still returns `200`

#### Scenario: Logout without a valid token
- **WHEN** a client calls `POST /api/auth/logout` with no token or an already revoked token
- **THEN** the response is `401` with `error.code` equal to `UNAUTHORIZED`

### Requirement: Change password
`POST /api/auth/change-password` SHALL require bearer authentication and accept `{ currentPassword, newPassword }` (`newPassword` 8–128 characters). When `currentPassword` is correct it SHALL store the new password hash, revoke **every** session of the user (including the one that made the request), create one new session, and respond `200` with `{ "token": string }` for that new session. When `currentPassword` is wrong it SHALL respond `403` with code `INVALID_PASSWORD` and change nothing.

#### Scenario: Successful change
- **WHEN** a user posts the correct `currentPassword` and a valid `newPassword`
- **THEN** the response is `200` with a non-empty `token`, login with the old password returns `401`, and login with the new password returns `200`

#### Scenario: All previous tokens are revoked
- **WHEN** a user with tokens `T1` and `T2` changes the password using `T1`
- **THEN** `GET /api/auth/me` returns `401` for both `T1` and `T2`, and `200` for the returned token

#### Scenario: Wrong current password
- **WHEN** a user posts an incorrect `currentPassword`
- **THEN** the response is `403` with `error.code` equal to `INVALID_PASSWORD`, the old password still logs in, and the calling token still works

#### Scenario: New password too short
- **WHEN** a user posts a 7-character `newPassword`
- **THEN** the response is `400` with `error.code` equal to `VALIDATION_ERROR` and the password is unchanged

### Requirement: Change email
`POST /api/auth/change-email` SHALL require bearer authentication and accept `{ newEmail, currentPassword }` (`newEmail` a valid email of at most 254 characters). The new email SHALL be stored lowercased and SHALL take effect immediately, without email verification.
- On success it SHALL respond `200` with the updated user object.
- If `currentPassword` is wrong it SHALL respond `403` with code `INVALID_PASSWORD`.
- If another user already has that email (compared case-insensitively) it SHALL respond `409` with code `EMAIL_TAKEN`.
- Submitting the caller's current email SHALL succeed without changes.
- A user without an email SHALL be able to add one this way.

The password check SHALL happen before the email-taken check. Existing sessions SHALL stay valid.

#### Scenario: Successful change
- **WHEN** a user posts `{ "newEmail": "New@Example.com", "currentPassword": "<correct>" }`
- **THEN** the response is `200` with `email` equal to `new@example.com`, and login works with the new email and fails with the old one

#### Scenario: Add an email
- **WHEN** a user registered without an email posts a new email and the correct password
- **THEN** the response is `200` with that email, and they can log in with it

#### Scenario: Wrong current password
- **WHEN** a user posts an incorrect `currentPassword`
- **THEN** the response is `403` with `error.code` equal to `INVALID_PASSWORD` and the email is unchanged

#### Scenario: Email already used
- **WHEN** a user posts the correct password and an email that another user registered (in any letter case)
- **THEN** the response is `409` with `error.code` equal to `EMAIL_TAKEN` and neither user is changed

#### Scenario: Wrong password and taken email
- **WHEN** a user posts an incorrect `currentPassword` and an email that another user registered
- **THEN** the response is `403` with `error.code` equal to `INVALID_PASSWORD`, not `409`

#### Scenario: Token keeps working
- **WHEN** a user changes the email and then calls `GET /api/auth/me` with the same token
- **THEN** the response is `200` with the new email

### Requirement: Password hashing
Passwords SHALL be hashed with argon2id before storage, with at least OWASP's minimum parameters (19 MiB memory, 2 iterations, parallelism 1) and a random salt per hash, in the self-describing PHC string format. Plaintext passwords SHALL NOT be stored or logged. When a login names an unknown user, the backend SHALL still verify the password against a fixed dummy hash, so the response time doesn't reveal whether the account exists.

#### Scenario: Stored hash is argon2id
- **WHEN** a user registers with password `P`
- **THEN** their stored hash starts with `$argon2id$`, is not equal to `P`, and differs from the hash of another user with the same password

#### Scenario: Unknown user takes as long as a wrong password
- **WHEN** a client logs in with an unknown username and, separately, with a known username and a wrong password
- **THEN** both requests verify one argon2id hash before answering `401`

### Requirement: Session tokens
A successful login or password change SHALL create a session whose token is at least 32 random bytes from a cryptographically secure generator, URL-safe encoded. The database SHALL store only the SHA-256 hash of the token, never the token itself.
- A session SHALL expire `SESSION_TTL_DAYS` (default 7) after it was last used. Using it SHALL extend the expiry, updating it at most once per day.
- Logout SHALL delete that session. A password change and account deletion SHALL delete all of the user's sessions.
- An expired, deleted or unknown token SHALL be treated like a missing one.

#### Scenario: Only the hash is stored
- **WHEN** a user logs in and receives token `T`
- **THEN** the `sessions` table contains the SHA-256 hash of `T` and no row contains `T` itself

#### Scenario: Sliding expiry
- **WHEN** a session is used more than a day after its expiry was last extended
- **THEN** its `expires_at` moves to `SESSION_TTL_DAYS` from now

#### Scenario: Expired session
- **WHEN** a session's `expires_at` is in the past and its token is used
- **THEN** the response is `401` with `error.code` equal to `UNAUTHORIZED`


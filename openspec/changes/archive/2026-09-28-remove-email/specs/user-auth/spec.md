## MODIFIED Requirements

### Requirement: User data model
The database SHALL contain the tables `users`, `user_passwords` and `sessions`, each with a UUID primary key (`user_passwords` uses `user_id` as its key).
- **`users`** SHALL have:
  - `username`: unique, not null, stored lowercased
  - `first_name`: not null
  - `last_name`: not null, may be empty
  - `created_at` and `updated_at` timestamps
- **`user_passwords`** SHALL hold the password hash, one row per user.
- **`sessions`** SHALL hold `token_hash` (unique), `user_id`, `expires_at` and timestamps.

The `users` table SHALL NOT have an `email` column. Password hashes SHALL be stored only in `user_passwords` and never on `users`. The `user_passwords.user_id` and `sessions.user_id` columns SHALL reference `users.id` with `ON DELETE CASCADE`.

#### Scenario: Registered user is stored with a UUID
- **WHEN** a user registers successfully
- **THEN** a `users` row exists whose `id` is a UUID, whose `first_name` and `last_name` match the request, and whose `username` is the requested username lowercased

#### Scenario: No email column
- **WHEN** the columns of the `users` table are inspected
- **THEN** there is no `email` column

#### Scenario: Password stored only as a hash
- **WHEN** a user registers with password `P`
- **THEN** exactly one `user_passwords` row for that user has a hash that is not equal to `P`, and the `users` table has no password column

#### Scenario: Deleting a user removes credentials and sessions
- **WHEN** a `users` row is deleted
- **THEN** all `user_passwords` and `sessions` rows referencing that user are deleted too

### Requirement: Password hashes are never returned
No endpoint SHALL ever include a password hash, or any field of the `user_passwords` or `sessions` tables other than the login token, in a response body, whether it succeeds or fails and whatever the environment. User objects in responses SHALL contain exactly these fields: `id`, `username`, `firstName`, `lastName`, `createdAt`, `updatedAt`.

#### Scenario: User objects expose only allow-listed fields
- **WHEN** any endpoint returns a user object
- **THEN** its keys are exactly `id`, `username`, `firstName`, `lastName`, `createdAt`, `updatedAt`

#### Scenario: No hash in any response
- **WHEN** every endpoint is called with both valid and invalid input
- **THEN** no response body contains a stored `user_passwords` hash, a `sessions.token_hash` value, or a key named `password`, `passwordHash` or `hash`

### Requirement: Register an account
`POST /api/auth/register` SHALL NOT require authentication. It SHALL accept `{ username, password, firstName?, lastName? }`, where:
- `username` has 3 to 30 characters that are letters, digits, `_` or `.`
- `password` has 8 to 128 characters
- `firstName` is a non-empty string and `lastName` a possibly empty string, each at most 100 characters

Without `firstName` it SHALL be the username, and without `lastName` it SHALL be empty. Other keys, including `email`, SHALL be ignored.

On success it SHALL create the user and respond `201` with the user object. It SHALL NOT return a token. If the username is already taken (compared case-insensitively), it SHALL respond `409` with code `USERNAME_TAKEN`. Usernames SHALL be stored lowercased.

#### Scenario: Successful registration
- **WHEN** a client posts `{ "username": "Ada_L", "password": "correct-horse", "firstName": "Ada", "lastName": "Lovelace" }`
- **THEN** the response is `201` with a user object whose `username` is `ada_l`, `firstName` is `Ada`, `lastName` is `Lovelace`, and `id` is a UUID, and the body has no `token` and no `email`

#### Scenario: Duplicate username
- **WHEN** a client posts `{ "username": "ADA_L", "password": "correct-horse" }` after `ada_l` already exists
- **THEN** the response is `409` with `error.code` equal to `USERNAME_TAKEN`

#### Scenario: Missing or invalid fields
- **WHEN** a client posts a body missing `password` or `username`, or with a 7-character password, or with a username that is shorter than 3 characters, longer than 30 or contains other characters than letters, digits, `_` and `.`
- **THEN** the response is `400` with `error.code` equal to `VALIDATION_ERROR` and no user is created

#### Scenario: Email only is rejected
- **WHEN** a client posts `{ "email": "a@example.com", "password": "correct-horse" }`
- **THEN** the response is `400` with `error.code` equal to `VALIDATION_ERROR`, because `username` is missing

#### Scenario: Unknown fields are not stored
- **WHEN** a client posts a valid body that also includes `"id": "<some uuid>"` and `"email": "a@example.com"`
- **THEN** the response is `201`, the user's `id` is not the one sent, and the response has no `email`

#### Scenario: Username and password only
- **WHEN** a client posts `{ "username": "Solo", "password": "correct-horse" }`
- **THEN** the response is `201` with `username` `solo`, `firstName` `solo` and `lastName` `""`

### Requirement: Log in
`POST /api/auth/login` SHALL NOT require authentication. It SHALL accept `{ username, password }`, where `username` is a non-empty string of at most 254 characters compared case-insensitively. It is not checked against the username rules, so a malformed username fails like an unknown one. A body without `username` or `password` SHALL be rejected with `400`; `identifier` and `email` SHALL NOT be accepted in place of `username`. With correct credentials it SHALL create a session and respond `200` with `{ "token": string, "user": User }`, where `token` works as a bearer token on protected endpoints. With an unknown or malformed username or a wrong password it SHALL respond `401` with code `INVALID_CREDENTIALS` and the message "Invalid username or password", and all these cases SHALL produce identical response bodies.

#### Scenario: Successful login
- **WHEN** a user registered with username `ada_l` posts `{ "username": "ADA_L", "password": <correct> }`
- **THEN** the response is `200` with a non-empty `token` and that user's user object

#### Scenario: Token works on protected routes
- **WHEN** the client calls `GET /api/auth/me` with `Authorization: Bearer <token from login>`
- **THEN** the response is `200`

#### Scenario: Wrong password
- **WHEN** a client posts a registered username with the wrong password
- **THEN** the response is `401` with `error.code` equal to `INVALID_CREDENTIALS`

#### Scenario: Unknown username is indistinguishable
- **WHEN** a client posts an unregistered username or a malformed username such as `a`
- **THEN** the response status and body are identical to the wrong-password case

#### Scenario: Old field names are rejected
- **WHEN** a client posts `{ "identifier": "ada_l", "password": <correct> }` or `{ "email": "ada_l", "password": <correct> }`
- **THEN** the response is `400` with `error.code` equal to `VALIDATION_ERROR`

#### Scenario: Login does not set cookies
- **WHEN** a login succeeds
- **THEN** the response has no `Set-Cookie` header

## REMOVED Requirements

### Requirement: Change email
**Reason**: Users no longer have an email address, so there is nothing to change.
**Migration**: None. `POST /api/auth/change-email` returns `404`, and the `EMAIL_TAKEN` error code no longer exists.

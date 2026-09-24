## ADDED Requirements

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
`POST /api/auth/change-password` SHALL require bearer authentication and accept `{ currentPassword, newPassword }` (strict; `newPassword` 8–128 characters). When `currentPassword` is correct it SHALL store the new password hash, revoke **every** session of the user (including the one that made the request), create one new session, and respond `200` with `{ "token": string }` for that new session. When `currentPassword` is wrong it SHALL respond `403` with code `INVALID_PASSWORD` and change nothing.

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
`POST /api/auth/change-email` SHALL require bearer authentication and accept `{ newEmail, currentPassword }` (strict; `newEmail` a valid email of at most 254 characters). The new email SHALL be stored lowercased and SHALL take effect immediately, without email verification. On success it SHALL respond `200` with the updated user object. If `currentPassword` is wrong it SHALL respond `403` with code `INVALID_PASSWORD`. If another user already has that email (compared case-insensitively) it SHALL respond `409` with code `EMAIL_TAKEN`. Submitting the caller's current email SHALL succeed without changes. The password check SHALL happen before the email-taken check. Existing sessions SHALL stay valid.

#### Scenario: Successful change
- **WHEN** a user posts `{ "newEmail": "New@Example.com", "currentPassword": "<correct>" }`
- **THEN** the response is `200` with `email` equal to `new@example.com`, and login works with the new email and fails with the old one

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

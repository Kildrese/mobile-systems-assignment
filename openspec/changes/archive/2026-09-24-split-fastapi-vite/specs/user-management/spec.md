## MODIFIED Requirements

### Requirement: Delete own user
`DELETE /api/users/:id` SHALL delete the caller's user record together with their password hash and sessions, and SHALL respond `204` with an empty body. After deletion, the caller's token SHALL no longer authenticate.

#### Scenario: Delete self
- **WHEN** user A calls `DELETE /api/users/<A's id>` with A's token
- **THEN** the response is `204` and A's `users`, `user_passwords` and `sessions` rows no longer exist

#### Scenario: Token invalid after deletion
- **WHEN** user A deletes their account and then calls `GET /api/auth/me` with the same token
- **THEN** the response is `401`

#### Scenario: Cannot log in after deletion
- **WHEN** user A deletes their account and then posts their old credentials to `/api/auth/login`
- **THEN** the response is `401` with `error.code` equal to `INVALID_CREDENTIALS`

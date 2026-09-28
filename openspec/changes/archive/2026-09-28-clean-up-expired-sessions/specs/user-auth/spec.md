## ADDED Requirements

### Requirement: Expired sessions are removed on login
A successful login SHALL delete every session of that user whose `expires_at` is in the past, in the same transaction that creates the new session. Sessions that have not expired, including the user's other active sessions, SHALL NOT be affected, and a failed login SHALL NOT delete anything.

#### Scenario: Expired sessions are deleted
- **WHEN** a user with one expired and one active session logs in successfully
- **THEN** the expired session row is gone, and the active session and the new one remain

#### Scenario: Other users are untouched
- **WHEN** a user logs in successfully while another user has an expired session
- **THEN** the other user's expired session row remains

#### Scenario: Failed login deletes nothing
- **WHEN** a user with an expired session tries to log in with a wrong password
- **THEN** the expired session row remains

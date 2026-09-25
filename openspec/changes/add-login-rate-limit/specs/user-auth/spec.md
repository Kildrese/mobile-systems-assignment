## ADDED Requirements

### Requirement: Login rate limiting
`POST /api/auth/login` SHALL count failed attempts per username (compared case-insensitively) and per client IP. After a failed attempt, the username SHALL be locked for `min(2^(n-1), 900)` seconds, where `n` is its number of consecutive failures. The client IP SHALL be locked the same way once it has more than the configured number of free failures (default 20). Failures SHALL be forgotten after one hour without a failure, and a successful login SHALL reset the username's count. While either the username or the client IP is locked, the endpoint SHALL respond `429` with code `RATE_LIMITED` and a `Retry-After` header giving the remaining seconds (at least 1), without verifying the password. Unknown and malformed usernames SHALL be counted and locked exactly like existing ones. The stored keys SHALL be SHA-256 digests, never the submitted username or the raw IP.

#### Scenario: Backoff after a failure
- **WHEN** a login for `ada` fails with a wrong password, and the client immediately tries again with the correct password
- **THEN** the second response is `429` with code `RATE_LIMITED` and a `Retry-After` header of at least 1

#### Scenario: Waits double
- **WHEN** a username has failed three times in a row
- **THEN** it is locked for 4 seconds after the third failure

#### Scenario: The wait is capped
- **WHEN** a username has failed twenty times in a row
- **THEN** it is locked for 900 seconds, not longer

#### Scenario: Login works after the wait
- **WHEN** a username's lock has expired and the correct password is sent
- **THEN** the response is `200`, and the username's failure count is reset

#### Scenario: Unknown usernames are indistinguishable
- **WHEN** an unknown username and an existing username each fail the same number of times
- **THEN** their next attempts get identical `429` responses, with the same `Retry-After`

#### Scenario: One IP spraying many usernames
- **WHEN** one client IP fails more than its free allowance across different usernames
- **THEN** its next login attempt, for any username, is `429`

#### Scenario: Other users are not affected by one user's lock
- **WHEN** `ada` is locked and `bob` logs in from another IP with the correct password
- **THEN** `bob` gets `200`

#### Scenario: Locked attempts do no password work
- **WHEN** a locked username sends a login
- **THEN** no user lookup and no password verification happen

#### Scenario: No raw usernames or IPs are stored
- **WHEN** the throttle table is inspected after failed logins
- **THEN** it contains neither the submitted usernames nor the client IPs, only their SHA-256 digests

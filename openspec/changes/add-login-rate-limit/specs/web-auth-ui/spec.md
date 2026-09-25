## ADDED Requirements

### Requirement: Login form handles rate limiting
When login answers `429 RATE_LIMITED`, the login form SHALL show "Too many attempts. Try again in N seconds.", where N is the `Retry-After` value, or "Too many attempts. Try again later." when the header is missing. It SHALL NOT clear the entered username.

#### Scenario: Locked out
- **WHEN** the user submits the login form and the API answers `429` with `Retry-After: 8`
- **THEN** the form shows "Too many attempts. Try again in 8 seconds." and keeps the username

## MODIFIED Requirements

### Requirement: Login page
`/login` SHALL be a full-page layout based on the shadcn `login-03` block: a muted full-screen background with the app name and a centred card holding a "Username" field and a password field, a submit button, and a link to `/register` that keeps the `next` parameter. It SHALL NOT show social-login buttons or a "forgot password" link, since neither exists. Signing in SHALL call `POST /api/auth/login` with `{ username, password }` and store the returned token (see `frontend-app`). Wrong credentials SHALL show one generic "Invalid username or password" message without revealing whether the account exists, and SHALL keep the entered username. The submit button SHALL be disabled while the request is pending.

#### Scenario: Successful sign-in
- **WHEN** a registered user enters correct credentials on `/login`
- **THEN** the token is stored and they are sent on (see "Safe post-login redirect")

#### Scenario: Wrong credentials
- **WHEN** a user enters an unknown username or a wrong password
- **THEN** the page shows "Invalid username or password", keeps the username field filled, and stores no token

#### Scenario: Invalid input
- **WHEN** a user submits an empty password or an empty username field
- **THEN** the field shows a validation message and no sign-in request is sent

### Requirement: Registration page
`/register` SHALL use the matching shadcn `signup-03` layout with first name (optional), last name (optional), username, password and confirm-password fields, and a link to `/login` that keeps the `next` parameter. It SHALL NOT ask for an email. It SHALL require the two passwords to match before sending anything. It SHALL show the API's validation errors on the matching fields.

On success (`POST /api/auth/register`) the app SHALL sign the user in immediately with `POST /api/auth/login`, store the token, and send them on as in "Safe post-login redirect". A taken username SHALL show an error on the username field.

#### Scenario: Successful registration
- **WHEN** a visitor fills in valid details on `/register`
- **THEN** the account is created, a token is stored, and they land on `/`

#### Scenario: No email field
- **WHEN** a visitor opens `/register`
- **THEN** the form has no email field

#### Scenario: Passwords don't match
- **WHEN** the password and confirm-password fields differ
- **THEN** the form shows an error and no request is sent

#### Scenario: Username taken
- **WHEN** a visitor registers with a username that already exists (any letter case)
- **THEN** the username field shows that the username is already taken and no token is stored

#### Scenario: Sign in with the username afterwards
- **WHEN** a user registered with username `ada_l` signs out and enters `ada_l` and the password on `/login`
- **THEN** they are signed in

### Requirement: Signed-in home page
`/` SHALL be a signed-in page that greets the user by first name and shows their `@username`. It SHALL link to `/account` and to the backend's API reference at `<VITE_API_URL>/docs`.

#### Scenario: Home greets the user
- **WHEN** a signed-in user named Ada opens `/`
- **THEN** the page shows a greeting containing "Ada", their `@username`, and links to `/account` and the API reference

### Requirement: App header and sign-out
Every signed-in page SHALL show a header with the app name (linking to `/`) and a user menu showing:
- the user's name and `@username`
- a link to `/account`
- a "Sign out" item

Signing out SHALL call `POST /api/auth/logout` with the token, remove the token even if that call fails, and navigate to `/login`.

#### Scenario: Sign out
- **WHEN** a signed-in user chooses "Sign out"
- **THEN** they land on `/login`, the token is gone from `localStorage`, the old token returns `401` on `GET /api/auth/me`, and opening `/account` afterwards shows the login page

### Requirement: Delete account in the UI
`/account` SHALL have a Danger zone card with a "Delete account" button that opens a confirmation dialog explaining that deletion is permanent. Confirming SHALL call `DELETE /api/users/:id` for the signed-in user, remove the token, and navigate to `/login`. Cancelling SHALL change nothing.

#### Scenario: Confirm deletion
- **WHEN** a user confirms account deletion
- **THEN** they land on `/login`, and signing in with the old credentials fails with "Invalid username or password"

#### Scenario: Cancel deletion
- **WHEN** a user opens the dialog and cancels
- **THEN** the dialog closes and the account still exists

## REMOVED Requirements

### Requirement: Change email in the UI
**Reason**: Users no longer have an email address.
**Migration**: None. The Email card is removed from `/account`; the Profile, Password and Danger zone cards remain.
